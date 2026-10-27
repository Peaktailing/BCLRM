#!/usr/bin/env python3
"""从指定 git sha 构建不可变 release（执行版第 3.3、6 节 Stage 0B）。

流程：``git archive`` 只导出已跟踪文件 → 校验必需资源 → 生成
requirements.lock 与离线 wheelhouse → 计算 payload 树哈希 → 写
release.json（不含 channel）→ 按 lock 建独立 ``.venv`` → 登记
releases-index.json。任何一步失败都清理临时目录，不留下“半个 release”。

用法：
    python scripts/build_release.py --version 0.8.19.1 --sha HEAD
    python scripts/build_release.py --version 0.8.19.1 --sha HEAD --skip-venv

退出码：0 成功；2 预检失败（版本复用、必需文件缺失等）；3 执行失败。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deploy import release_layout as layout  # noqa: E402

#: 制品必需资源：缺任何一项都不允许发版（D：用户手册/主题/品牌资源）
REQUIRED_PATHS = (
    "docs/用户使用手册.md",
    ".streamlit/config.toml",
    "assets",
)
#: 部署器依赖的稳定 CLI；缺失时部署必然失败，构建阶段显式告警
RECOMMENDED_PATHS = ("scripts/runtime_cli.py", "app.py")


def _run(command: List[str], *, cwd: Optional[Path] = None,
         timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, timeout=timeout,
    )


def pip_freeze(python: str) -> str:
    result = _run([python, "-m", "pip", "freeze", "--disable-pip-version-check"])
    if result.returncode != 0:
        raise layout.ExecutionFailure(f"pip freeze 失败：{result.stderr.strip()}")
    return result.stdout.strip() + "\n"


def parse_lock(text: str) -> Dict[str, str]:
    """只解析 ``name==version`` 行；其余（-e、旧式 URL）不参与 wheel 解析。"""
    dists = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        name = name.split("[", 1)[0].strip()
        version = version.split(";", 1)[0].strip()
        if name and version:
            dists[_normalize_name(name)] = version
    return dists


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _wheel_identity(path: Path) -> Optional[Tuple[str, str]]:
    """从 wheel 文件名取 (规范化分发名, 版本)；解析不了返回 None。

    不引入 packaging 依赖：wheel 文件名规范保证 distribution 段不含连字符，
    因此按 ``-`` 切分前两段即可，且分布式名需把下划线还原成连字符。
    """
    name = path.name
    if not name.endswith(".whl"):
        return None
    parts = name[:-4].split("-")
    if len(parts) < 5:
        return None
    return parts[0].replace("_", "-").lower(), parts[1]


def _wheel_candidates(sources: List[Path]) -> Dict[Tuple[str, str], Path]:
    found: Dict[Tuple[str, str], Path] = {}
    for source in sources:
        if not source or not Path(source).is_dir():
            continue
        for wheel in sorted(Path(source).rglob("*.whl")):
            identity = _wheel_identity(wheel)
            if identity and identity not in found:
                found[identity] = wheel
    return found


def _pip_cache_dirs(python: str) -> List[Path]:
    result = _run([python, "-m", "pip", "cache", "dir",
                   "--disable-pip-version-check"])
    if result.returncode != 0:
        return []
    root = Path(result.stdout.strip())
    if not root.is_dir():
        return []
    wheels = root / "wheels"
    return [wheels] if wheels.is_dir() else [root]


def collect_wheelhouse(
    lock_text: str,
    destination: Path,
    *,
    python: str,
    cache_sources: List[Path],
    offline: bool,
) -> Dict[str, object]:
    """把 lock 里每个分发收集成 wheel；离线时必须全部命中本地缓存。

    先扫描显式缓存目录与 pip 缓存，缺失的才联网 ``pip download``。这样在
    有网机器上能补齐，在无网机器上失败信息会明确列出“缺哪些 wheel”。
    """
    dists = parse_lock(lock_text)
    if not dists:
        raise layout.ExecutionFailure("requirements.lock 没有任何 name==version 行")
    destination.mkdir(parents=True, exist_ok=True)
    sources = [Path(p) for p in cache_sources if p]
    found = _wheel_candidates(sources + _pip_cache_dirs(python))
    copied: List[str] = []
    missing = []
    for name, version in sorted(dists.items()):
        wheel = found.get((name, version))
        if wheel is None:
            missing.append(f"{name}=={version}")
            continue
        target = destination / wheel.name
        if not target.exists():
            shutil.copy2(wheel, target)
        copied.append(wheel.name)

    if missing and not offline:
        lock_file = destination / ".requirements.lock"
        lock_file.write_text(lock_text, encoding="utf-8")
        result = _run([
            python, "-m", "pip", "download", "--disable-pip-version-check",
            "--only-binary=:all:", "--dest", str(destination),
            "-r", str(lock_file),
        ], timeout=1800)
        lock_file.unlink(missing_ok=True)
        if result.returncode != 0:
            print(f"[WARN] pip download 失败：{result.stderr.strip()[-500:]}")
        found = _wheel_candidates([destination] + sources + _pip_cache_dirs(python))
        still_missing = []
        for item in missing:
            name, version = item.split("==", 1)
            wheel = found.get((_normalize_name(name), version))
            if wheel is None:
                still_missing.append(item)
            elif not (destination / wheel.name).exists():
                shutil.copy2(wheel, destination)
        missing = still_missing

    if missing:
        raise layout.ExecutionFailure(
            "离线 wheelhouse 不完整，缺少：" + ", ".join(missing)
            + "（请在有网环境补齐 --wheelhouse-cache，或清理 pip 缓存前先归档）"
        )
    return {"wheels": len(copied), "destination": str(destination)}


def read_schema_versions(repo: Path) -> Dict[str, int]:
    """从 db/schema_guard.py 常量推导四库版本，避免手写 map 漂移。"""
    path = Path(repo) / "db" / "schema_guard.py"
    if not path.is_file():
        raise layout.LayoutError(f"找不到 schema_guard.py：{path}")
    text = path.read_text(encoding="utf-8")
    main_match = re.search(r"^MAIN_SCHEMA_VERSION\s*=\s*(\d+)", text, re.M)
    aux_match = re.search(r"^AUX_SCHEMA_VERSION\s*=\s*(\d+)", text, re.M)
    if not main_match or not aux_match:
        raise layout.LayoutError("schema_guard.py 缺少 MAIN/AUX_SCHEMA_VERSION 常量")
    main_version = int(main_match.group(1))
    aux_version = int(aux_match.group(1))
    return {
        "main.db": main_version,
        "archive_cold.db": aux_version,
        "attach_cold.db": aux_version,
        "operation_log.db": aux_version,
    }


def assert_required_payload(payload: Path) -> None:
    missing = []
    for rel in REQUIRED_PATHS:
        target = payload / rel
        if rel == "assets":
            if not target.is_dir() or not any(target.rglob("*")):
                missing.append(rel)
        elif not target.is_file():
            missing.append(rel)
    if missing:
        raise layout.LayoutError(
            "payload 缺少发版必需内容（git archive 只含已跟踪文件）："
            + ", ".join(missing)
        )
    for rel in RECOMMENDED_PATHS:
        if not (payload / rel).is_file():
            print(f"[WARN] payload 缺少 {rel}，部署/迁移会失败；请确认该文件已提交")


def _extract_archive(archive: Path, payload: Path) -> None:
    payload.mkdir(parents=True)
    layout.safe_extract_tar(archive, payload)


def _build_venv(release: Path, lock_path: Path, wheelhouse: Path,
                python: str, use_wheelhouse: bool) -> None:
    venv = release / ".venv"
    result = _run([python, "-m", "venv", str(venv)], timeout=300)
    if result.returncode != 0:
        raise layout.ExecutionFailure(f"创建 venv 失败：{result.stderr.strip()}")
    pip = venv / "bin" / "pip"
    command = [str(pip), "install", "--disable-pip-version-check", "-r", str(lock_path)]
    if use_wheelhouse:
        command[2:2] = ["--no-index", "--find-links", str(wheelhouse)]
    result = _run(command, timeout=3600)
    if result.returncode != 0:
        raise layout.ExecutionFailure(
            "按 lock 安装依赖失败（离线 wheelhouse 不完整？）："
            + result.stderr.strip()[-800:]
        )
    check = _run([str(venv / "bin" / "python"), "-c",
                  "import sys;print(sys.version.split()[0])"])
    if check.returncode != 0:
        raise layout.ExecutionFailure("新建 venv 无法运行")
    if check.stdout.strip() != layout.REQUIRED_PYTHON:
        raise layout.ExecutionFailure(
            f"venv Python 版本为 {check.stdout.strip()}，要求 {layout.REQUIRED_PYTHON}"
        )


def build(
    *,
    root: Path,
    repo: Path,
    version: str,
    sha: str,
    python: str,
    skip_venv: bool,
    skip_wheelhouse: bool,
    offline: bool,
    wheelhouse_caches: List[Path],
    schema_override: Optional[Path],
) -> Dict[str, object]:
    root = Path(root).resolve()
    repo = Path(repo).resolve()
    version = layout.normalize_version(version)
    layout.reject_version_reuse(root, version)

    commit = layout.resolve_commit(repo, sha)
    releases = layout.releases_dir(root)
    releases.mkdir(parents=True, exist_ok=True)
    staging = releases / f".build-{version}-{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    final = layout.release_dir(root, version)

    try:
        # 1) git archive：只含已跟踪文件，工作区未提交改动不会混入制品
        archive = staging / "payload.tar"
        result = _run(["git", "-C", str(repo), "archive", "--format=tar",
                       "-o", str(archive), commit], timeout=300)
        if result.returncode != 0:
            raise layout.ExecutionFailure(
                f"git archive 失败：{result.stderr.strip()}"
            )
        payload = staging / "payload"
        _extract_archive(archive, payload)
        archive.unlink()
        assert_required_payload(payload)

        # 2) lock 与离线 wheelhouse（D07）
        lock_text = pip_freeze(python)
        lock_path = payload / "requirements.lock"
        lock_path.write_text(lock_text, encoding="utf-8")
        lock_sha = layout.hash_file(lock_path)

        wheelhouse = staging / "wheelhouse"
        wheel_report = {"wheels": 0, "destination": None}
        if skip_wheelhouse:
            print("[WARN] --skip-wheelhouse：该 release 无法保证离线重建，仅供测试")
        else:
            caches = list(wheelhouse_caches) + [root / "wheelhouse"]
            wheel_report = collect_wheelhouse(
                lock_text, wheelhouse, python=python,
                cache_sources=caches, offline=offline,
            )

        # 3) 制品哈希（不含 .venv / release.json）
        artifact_sha = layout.payload_sha256(payload)

        # 4) schema map：默认从代码常量推导，允许显式覆盖
        if schema_override:
            schema_doc = layout.read_json(Path(schema_override))
            schema_versions = {
                name: int(value) for name, value in schema_doc.items()
            }
        else:
            schema_versions = read_schema_versions(repo)
        for name in layout.DB_NAMES:
            if schema_versions.get(name) is None:
                raise layout.LayoutError(f"schema map 缺少 {name}")

        doc = {
            "version": version,
            "git_sha": commit,
            "artifact_sha256": artifact_sha,
            "python_version": layout.REQUIRED_PYTHON,
            "requirements_lock_sha256": lock_sha,
            "schema_versions": schema_versions,
            "built_at": layout.utc_now_iso(),
        }
        layout.validate_release_doc(doc)
        layout.write_json_atomic(staging / "release.json", doc)

        # 5) 独立 venv
        if skip_venv:
            print("[INFO] --skip-venv：跳过依赖安装")
        else:
            _build_venv(staging, staging / "payload" / "requirements.lock",
                        wheelhouse, python,
                        use_wheelhouse=not skip_wheelhouse)

        if final.exists():
            raise layout.LayoutError(f"release 目录在构建期间被占用：{final}")
        os.replace(staging, final)
        try:
            layout.record_build(root, doc, final)
        except Exception:
            # 台账写失败不能留下“目录存在但未登记”的版本，否则会诱发复用
            shutil.rmtree(final, ignore_errors=True)
            raise
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return {
        "version": version,
        "release": str(final),
        "git_sha": commit,
        "artifact_sha256": artifact_sha,
        "requirements_lock_sha256": lock_sha,
        "wheelhouse": wheel_report,
        "venv": str(final / ".venv") if not skip_venv else None,
        "schema_versions": schema_versions,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="从 git sha 构建不可变 release（只含已跟踪文件）"
    )
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT),
                        help="部署根（测试必须传临时目录）")
    parser.add_argument("--repo", default=str(PROJECT_ROOT),
                        help="源码 git 仓库根，默认脚本所在仓库")
    parser.add_argument("--version", required=True, help="四段版本号，如 0.8.19.1")
    parser.add_argument("--sha", default="HEAD", help="构建提交（默认 HEAD）")
    parser.add_argument("--python", default=sys.executable,
                        help="构建解释器（必须 3.10.12）")
    parser.add_argument("--skip-venv", action="store_true",
                        help="跳过 .venv 创建（测试用，不用于真实发布）")
    parser.add_argument("--skip-wheelhouse", action="store_true",
                        help="跳过离线 wheelhouse 收集（测试用）")
    parser.add_argument("--offline", action="store_true",
                        help="只使用本地 wheel 缓存，缺失即失败")
    parser.add_argument("--wheelhouse-cache", action="append", default=[],
                        type=Path, help="已有 wheel 的目录，可重复")
    parser.add_argument("--schema-json", type=Path,
                        help="覆盖 schema map 的 JSON（默认读 schema_guard 常量）")
    args = parser.parse_args(argv)

    try:
        python_version = _run([args.python, "-c",
                               "import sys;print(sys.version.split()[0])"])
        actual = python_version.stdout.strip()
        if python_version.returncode != 0 or actual != layout.REQUIRED_PYTHON:
            raise layout.LayoutError(
                f"构建解释器为 {actual or '不可用'}，统一要求 {layout.REQUIRED_PYTHON}"
            )
        result = build(
            root=Path(args.root), repo=Path(args.repo), version=args.version,
            sha=args.sha, python=args.python, skip_venv=args.skip_venv,
            skip_wheelhouse=args.skip_wheelhouse, offline=args.offline,
            wheelhouse_caches=[Path(p) for p in args.wheelhouse_cache],
            schema_override=args.schema_json,
        )
    except layout.LayoutError as exc:
        print(f"[FAIL] 预检失败：{exc}")
        return 2
    except (layout.ExecutionFailure, OSError, subprocess.SubprocessError,
            tarfile.TarError) as exc:
        print(f"[FAIL] 构建失败：{exc}")
        return 3

    print(f"[ OK ] release {result['version']} -> {result['release']}")
    print(f"[INFO] git_sha={result['git_sha']}")
    print(f"[INFO] artifact_sha256={result['artifact_sha256']}")
    print(f"[INFO] requirements_lock_sha256={result['requirements_lock_sha256']}")
    if result["wheelhouse"].get("destination"):
        print(f"[INFO] wheelhouse={result['wheelhouse']['destination']} "
              f"({result['wheelhouse']['wheels']} wheels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
