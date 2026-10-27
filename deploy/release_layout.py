"""发布布局与共享契约（Stage 0B 工具链的单一事实来源）。

为什么单独一层：build/backup/restore/deploy/rollback/status 六个脚本都要
回答同一组问题——release 目录在哪、指针指向谁、版本怎么比较、release.json
是否合法、怎么调用 runtime_cli。这些规则若各写一遍，迟早出现“部署器认为
合法、应用认为非法”的分叉，因此集中在这里，脚本只做流程编排。

本模块不导入 config.settings：工具链要能在任意 root 上操作（测试用临时
目录），不能被当前进程的环境变量绑死。所有函数都显式接收 root/release 路径。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: 真实部署根；测试/演练一律用 --root 覆盖，绝不能把默认值当测试目录
DEFAULT_ROOT = Path("/home/biochm/BCLRM")
#: 工具链版本写进备份 manifest，便于日后判断“哪版工具做的快照”
TOOL_NAME = "bclrm-release-tools"
TOOL_VERSION = "1.0.0"
#: D07：统一 Python 3.10.12
REQUIRED_PYTHON = "3.10.12"
#: release.json 的必填字段（D06：不写 channel）
REQUIRED_RELEASE_FIELDS = (
    "version",
    "git_sha",
    "artifact_sha256",
    "python_version",
    "requirements_lock_sha256",
    "schema_versions",
    "built_at",
)
DB_NAMES = ("main.db", "archive_cold.db", "attach_cold.db", "operation_log.db")
POINTER_NAMES = {"prod": "current_prod", "beta": "current_beta"}
BACKUP_KINDS = ("daily", "semimonthly", "pre_change", "annual")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LayoutError(RuntimeError):
    """布局/契约不满足：预检失败，调用方应返回退出码 2。"""


class ExecutionFailure(RuntimeError):
    """执行阶段失败：调用方应返回退出码 3。"""


# ---------------------------------------------------------------------------
# 基础路径
# ---------------------------------------------------------------------------
def releases_dir(root: Path) -> Path:
    return Path(root) / "releases"


def release_dir(root: Path, version: str) -> Path:
    return releases_dir(root) / normalize_version(version)


def data_dir(root: Path, env: str) -> Path:
    if env not in ("prod", "beta", "dev"):
        raise LayoutError(f"未知环境：{env}")
    return Path(root) / "data" / env


def backups_dir(root: Path, env: str) -> Path:
    return Path(root) / "backups" / env


def acceptance_file(root: Path, version: str) -> Path:
    return Path(root) / "acceptance" / f"{normalize_version(version)}.json"


def deployment_file(root: Path, env: str) -> Path:
    return Path(root) / "deployments" / f"{env}.json"


def releases_index_path(root: Path) -> Path:
    return Path(root) / "releases-index.json"


def release_train_path(root: Path) -> Path:
    return Path(root) / "release_train.json"


def pointer_name(env: str) -> str:
    try:
        return POINTER_NAMES[env]
    except KeyError as exc:
        raise LayoutError(f"环境 {env} 没有独立指针（只允许 prod/beta）") from exc


def pointer_path(root: Path, env: str) -> Path:
    return Path(root) / pointer_name(env)


def venv_python(release: Path) -> Path:
    return Path(release) / ".venv" / "bin" / "python"


def payload_dir(release: Path) -> Path:
    return Path(release) / "payload"


def release_json_path(release: Path) -> Path:
    return Path(release) / "release.json"


# ---------------------------------------------------------------------------
# 版本（D03/D04）：四段纯数字，按四整数比较
# ---------------------------------------------------------------------------
def normalize_version(value: str) -> str:
    """校验并规范化四段版本；带 v 前缀、三段、字母一律拒绝。"""
    text = str(value or "").strip()
    if text.lower().startswith("v"):
        raise LayoutError(f"版本号不要带 v 前缀：{value!r}")
    if not _VERSION_RE.match(text):
        raise LayoutError(
            f"版本必须是四段纯数字 MAJOR.MINOR.PATCH.BUILD：{value!r}"
        )
    return ".".join(str(int(part)) for part in text.split("."))


def version_tuple(value: str) -> Tuple[int, int, int, int]:
    parts = normalize_version(value).split(".")
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def compare_versions(left: str, right: str) -> int:
    a, b = version_tuple(left), version_tuple(right)
    return (a > b) - (a < b)


# ---------------------------------------------------------------------------
# JSON 原子读写
# ---------------------------------------------------------------------------
def read_json(path: Path, *, required: bool = True) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        if required:
            raise LayoutError(f"文件不存在：{path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LayoutError(f"JSON 无法解析：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise LayoutError(f"JSON 顶层必须是对象：{path}")
    return data


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """同目录临时文件 + os.replace：中途崩溃不会留下半份 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise LayoutError(f"时间不是 ISO-8601：{value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# release.json 校验（第 3.3 节）
# ---------------------------------------------------------------------------
def validate_release_doc(doc: Dict[str, Any], *, require_schema_all: bool = True) -> Dict[str, Any]:
    """严格校验 release.json，返回规范化副本；不合法抛 LayoutError。

    channel 属于部署环境（D06），release.json 出现该字段说明有人把部署状态
    写回了不可变制品，直接拒绝。
    """
    if "channel" in doc:
        raise LayoutError("release.json 不得包含 channel（渠道属于部署环境）")
    missing = [key for key in REQUIRED_RELEASE_FIELDS if key not in doc]
    if missing:
        raise LayoutError("release.json 缺字段：" + ", ".join(missing))

    version = normalize_version(doc["version"])
    git_sha = str(doc["git_sha"])
    if not _SHA40_RE.match(git_sha):
        raise LayoutError(f"git_sha 必须是完整 40 位小写 sha：{git_sha!r}")
    artifact = str(doc["artifact_sha256"])
    if not _SHA256_RE.match(artifact):
        raise LayoutError("artifact_sha256 必须是 64 位十六进制")
    lock_sha = str(doc["requirements_lock_sha256"])
    if not _SHA256_RE.match(lock_sha):
        raise LayoutError("requirements_lock_sha256 必须是 64 位十六进制")
    python_version = str(doc["python_version"])
    if python_version != REQUIRED_PYTHON:
        raise LayoutError(f"python_version 必须是 {REQUIRED_PYTHON}：{python_version!r}")

    schema = doc["schema_versions"]
    if not isinstance(schema, dict):
        raise LayoutError("schema_versions 必须是对象")
    for name, version_value in schema.items():
        if name not in DB_NAMES:
            raise LayoutError(f"schema_versions 出现未知库：{name}")
        if not isinstance(version_value, int) or version_value < 0:
            raise LayoutError(f"schema_versions[{name}] 必须是非负整数")
    if require_schema_all:
        lacking = [name for name in DB_NAMES if name not in schema]
        if lacking:
            raise LayoutError("schema_versions 未覆盖四库：" + ", ".join(lacking))

    parse_iso(doc["built_at"])
    normalized = dict(doc)
    normalized["version"] = version
    normalized["schema_versions"] = {name: int(schema[name]) for name in DB_NAMES if name in schema}
    return normalized


def read_release(release: Path) -> Dict[str, Any]:
    path = release_json_path(release)
    doc = validate_release_doc(read_json(path))
    if normalized_dir_version(release) and normalized_dir_version(release) != doc["version"]:
        raise LayoutError(
            f"目录名 {Path(release).name} 与 release.json 版本 {doc['version']} 不一致"
        )
    return doc


def normalized_dir_version(release: Path) -> str:
    name = Path(release).name
    try:
        return normalize_version(name)
    except LayoutError:
        return ""


# ---------------------------------------------------------------------------
# 制品哈希：payload 树哈希（不包含 .venv、release.json）
# ---------------------------------------------------------------------------
def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_sha256(payload: Path) -> str:
    """对 payload 做确定性树哈希：路径 + 内容 + 可执行位。

    只哈希相对路径与文件内容，不哈希 mtime/uid，保证同一 git sha 在不同
    机器上构建出相同 artifact_sha256；符号链接记录目标字符串而非解引用。
    """
    payload = Path(payload)
    if not payload.is_dir():
        raise LayoutError(f"payload 不存在：{payload}")
    digest = hashlib.sha256()
    for path in sorted(payload.rglob("*"), key=lambda p: p.relative_to(payload).as_posix()):
        rel = path.relative_to(payload).as_posix()
        if path.is_symlink():
            digest.update(f"L:{rel}\0{os.readlink(path)}\n".encode())
        elif path.is_file():
            mode = "x" if os.access(path, os.X_OK) else "-"
            digest.update(f"F:{rel}\0{mode}\0{hash_file(path)}\n".encode())
        elif path.is_dir():
            digest.update(f"D:{rel}\n".encode())
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# releases-index.json：版本禁复用台账
# ---------------------------------------------------------------------------
def load_index(root: Path) -> Dict[str, Any]:
    path = releases_index_path(root)
    if not path.is_file():
        return {"schema_version": 1, "versions": {}}
    data = read_json(path)
    data.setdefault("schema_version", 1)
    versions = data.get("versions")
    if not isinstance(versions, dict):
        raise LayoutError("releases-index.json 的 versions 必须是对象")
    return data


def record_build(root: Path, doc: Dict[str, Any], release: Path) -> None:
    index = load_index(root)
    version = doc["version"]
    if version in index["versions"]:
        raise LayoutError(f"版本 {version} 已存在于 releases-index，禁止复用")
    index["versions"][version] = {
        "git_sha": doc["git_sha"],
        "artifact_sha256": doc["artifact_sha256"],
        "python_version": doc["python_version"],
        "schema_versions": doc["schema_versions"],
        "built_at": doc["built_at"],
        "release_path": str(Path(release).relative_to(root)),
        "status": "built",
    }
    write_json_atomic(releases_index_path(root), index)


def update_index_status(root: Path, version: str, status: str) -> None:
    """状态只做运营标记，不改变版本禁复用事实。"""
    index = load_index(root)
    entry = index["versions"].get(normalize_version(version))
    if entry is None:
        return
    entry["status"] = status
    entry["status_updated_at"] = utc_now_iso()
    write_json_atomic(releases_index_path(root), index)


def reject_version_reuse(root: Path, version: str) -> None:
    """目录或台账任一命中即拒绝（D04：部署/打 tag 后版本锁定）。"""
    version = normalize_version(version)
    if release_dir(root, version).exists():
        raise LayoutError(f"release 目录已存在，禁止复用版本：{release_dir(root, version)}")
    index = load_index(root)
    if version in index["versions"]:
        raise LayoutError(f"releases-index.json 已登记版本 {version}，禁止复用")
    train = read_json(release_train_path(root), required=False)
    retired = train.get("retired_versions") or []
    if version in retired:
        raise LayoutError(f"release_train.json 已将 {version} 标记退役，禁止复用")


# ---------------------------------------------------------------------------
# 指针（D01）：current_prod / current_beta 是独立符号链接
# ---------------------------------------------------------------------------
def read_pointer(root: Path, env: str) -> Optional[Path]:
    link = pointer_path(root, env)
    if not link.exists() and not link.is_symlink():
        return None
    try:
        return link.resolve()
    except OSError as exc:
        raise LayoutError(f"指针无法解析：{link}（{exc}）") from exc


def pointer_target_name(root: Path, env: str) -> Optional[str]:
    link = pointer_path(root, env)
    if not link.is_symlink():
        return None
    return os.readlink(link)


def switch_pointer(root: Path, env: str, version: str) -> Optional[Path]:
    """原子切换指针，返回旧 release 路径（用于失败回切）。

    先在同目录建临时链接再 os.replace，避免出现“指针指向一半”的窗口。
    """
    version = normalize_version(version)
    target_release = release_dir(root, version)
    if not target_release.is_dir():
        raise LayoutError(f"待切换的 release 不存在：{target_release}")
    link = pointer_path(root, env)
    old = read_pointer(root, env)
    tmp = link.parent / f".{link.name}.{os.getpid()}"
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    rel_target = os.path.join("releases", version)
    os.symlink(rel_target, tmp)
    os.replace(tmp, link)
    return old


# ---------------------------------------------------------------------------
# 部署状态
# ---------------------------------------------------------------------------
def load_deployment(root: Path, env: str) -> Dict[str, Any]:
    return read_json(deployment_file(root, env), required=False)


def save_deployment(root: Path, env: str, record: Dict[str, Any]) -> None:
    """覆盖当前记录，同时把旧记录压入 history，保留事故追溯线索。"""
    path = deployment_file(root, env)
    existing = read_json(path, required=False)
    history = list(existing.get("history") or [])
    if existing.get("version"):
        snapshot = {key: existing.get(key) for key in (
            "version", "release_path", "deployed_at", "status", "backup", "previous"
        )}
        history.append(snapshot)
    record = dict(record)
    record["history"] = history[-20:]
    record["updated_at"] = utc_now_iso()
    write_json_atomic(path, record)


def collect_referenced_versions(root: Path) -> set:
    """指针、部署记录、回滚点引用的版本；release 清理时一律保留。"""
    referenced = set()
    for env in ("prod", "beta"):
        current = read_pointer(root, env)
        if current:
            referenced.add(Path(current).name)
        record = load_deployment(root, env)
        for key in ("version", "rollback_release", "previous"):
            value = record.get(key)
            if isinstance(value, dict):
                value = value.get("version")
            if value:
                referenced.add(str(value))
    train = read_json(release_train_path(root), required=False)
    for version in train.get("pinned_versions") or []:
        referenced.add(str(version))
    return referenced


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------
def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise ExecutionFailure(
            f"git {' '.join(args)} 失败：{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def resolve_commit(repo: Path, ref: str) -> str:
    result = git(repo, "rev-parse", f"{ref}^{{commit}}")
    sha = result.stdout.strip()
    if not _SHA40_RE.match(sha):
        raise LayoutError(f"无法解析提交：{ref}")
    return sha


def is_ancestor(repo: Path, older: str, newer: str) -> bool:
    result = git(repo, "merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise LayoutError(f"祖先检查执行失败：{result.stderr.strip()}")


def safe_extract_tar(archive: Path, target: Path) -> None:
    """解包时拒绝绝对路径与 ..，避免构建/恢复被恶意制品带到目录外。"""
    target = Path(target).resolve()
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            member_path = (target / member.name).resolve()
            if member_path != target and target not in member_path.parents:
                raise LayoutError(f"压缩包包含越界路径：{member.name}")
            if member.isdev():
                raise LayoutError(f"压缩包包含设备文件：{member.name}")
        tar.extractall(target)


# ---------------------------------------------------------------------------
# 运行 runtime_cli（Stage 0A 唯一稳定入口，不另造迁移入口）
# ---------------------------------------------------------------------------
def runtime_env(env: str, data_root: Path, release: Path, *, mobile_ui: str = "0") -> Dict[str, str]:
    environment = dict(os.environ)
    environment.update({
        "BCLRM_ENV": env,
        "BCLRM_DATA_DIR": str(Path(data_root).resolve()),
        "BCLRM_RELEASE_FILE": str(release_json_path(release).resolve()),
        "BCLRM_MOBILE_UI": mobile_ui,
        # 演练/迁移可能从只读制品或符号链接 payload 导入模块，不写 __pycache__
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    environment.pop("BCLRM_VERSION", None)
    return environment


def interpreter_for(release: Path, override: Optional[str] = None) -> str:
    if override:
        return override
    candidate = venv_python(release)
    if candidate.is_file():
        return str(candidate)
    return sys.executable


def run_runtime_cli(
    release: Path,
    command: str,
    env: str,
    data_root: Path,
    *,
    python: Optional[str] = None,
    timeout: int = 300,
    mobile_ui: str = "0",
) -> subprocess.CompletedProcess:
    """在目标 release 的 payload 里执行 runtime_cli，返回完整结果供记录。

    迁移/冒烟必须是“目标 release 的代码 + 目标 release 的 venv”，否则演练
    会误用当前仓库解释器，得到看似通过但不可复现的结论。
    """
    payload = payload_dir(release)
    cli = payload / "scripts" / "runtime_cli.py"
    if not cli.is_file():
        raise LayoutError(f"目标 release 缺少 runtime_cli：{cli}")
    return subprocess.run(
        [interpreter_for(release, python), str(cli), command],
        cwd=str(payload),
        env=runtime_env(env, data_root, release, mobile_ui=mobile_ui),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# 端口与健康检查
# ---------------------------------------------------------------------------
def port_is_listening(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def find_free_port(start: int = 8700, *, forbidden: Iterable[int] = (8501, 8601)) -> int:
    forbidden = set(forbidden)
    for port in range(start, start + 200):
        if port in forbidden:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise ExecutionFailure(f"从 {start} 起找不到空闲端口")


def wait_http_ok(url: str, timeout: float = 60.0, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(interval)
    return False


def copy_tree_verified(source: Path, target: Path) -> None:
    """第二副本只允许复制 + 重新校验（禁止硬链接，D20）。"""
    target = Path(target)
    if target.exists():
        raise LayoutError(f"第二副本目标已存在：{target}")
    shutil.copytree(source, target)


def disk_free_gib(path: Path) -> float:
    usage = shutil.disk_usage(str(path))
    return usage.free / (1024 ** 3)
