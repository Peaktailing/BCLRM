#!/usr/bin/env python3
"""发布状态总览/门禁（执行版 3.4、5.3）。

输出两轨（prod/beta）的指针、版本、git sha、artifact sha、schema、部署时间、
观察期与祖先关系；所有版本比较统一走四整数元组（D03），并用
releases-index.json + release_train.json 检查“版本是否被复用/已退役”。

``--check`` 作为晋升门禁：prod 版本必须低于 beta、artifact 哈希必须与
release.json 一致、prod sha 必须是 beta sha 的祖先；不满足退出码 2。

用法：
    python scripts/release_status.py
    python scripts/release_status.py --check --verify-artifacts

退出码：0 正常；2 门禁不通过；3 读取执行错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deploy import release_layout as layout  # noqa: E402

OBSERVATION_DAYS = 3


def _track(root: Path, env: str, verify_artifacts: bool,
           warnings: List[str]) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "env": env,
        "pointer": layout.pointer_name(env),
        "release_path": None,
        "version": None,
        "git_sha": None,
        "artifact_sha256": None,
        "artifact_verified": None,
        "schema_versions": None,
        "deployed_at": None,
        "status": "absent",
    }
    release = layout.read_pointer(root, env)
    if release is None:
        return info
    info["release_path"] = str(release)
    try:
        doc = layout.read_release(release)
    except (layout.LayoutError, OSError) as exc:
        warnings.append(f"{env} release 不可读：{exc}")
        info["status"] = "broken"
        return info
    info.update({
        "version": doc["version"],
        "git_sha": doc["git_sha"],
        "artifact_sha256": doc["artifact_sha256"],
        "schema_versions": doc["schema_versions"],
        "status": "deployed",
    })
    if verify_artifacts:
        try:
            actual = layout.payload_sha256(layout.payload_dir(release))
            info["artifact_verified"] = actual == doc["artifact_sha256"]
            if actual != doc["artifact_sha256"]:
                warnings.append(f"{env} payload 哈希与 release.json 不一致")
        except (layout.LayoutError, OSError) as exc:
            info["artifact_verified"] = False
            warnings.append(f"{env} 无法校验制品：{exc}")

    deployment = layout.load_deployment(root, env)
    info["deployed_at"] = deployment.get("deployed_at")
    if deployment.get("version") != doc["version"]:
        warnings.append(
            f"{env} 指针版本 {doc['version']} 与部署记录 "
            f"{deployment.get('version')} 不一致"
        )
    index = layout.load_index(root)
    if doc["version"] not in index["versions"]:
        warnings.append(f"{env} 版本 {doc['version']} 未在 releases-index 登记")
    else:
        entry = index["versions"][doc["version"]]
        if entry.get("artifact_sha256") != doc["artifact_sha256"]:
            warnings.append(f"{env} 版本 {doc['version']} 台账 artifact 哈希不一致")
    return info


def collect_status(root: Path, repo: Path, *,
                   verify_artifacts: bool, observation_days: int) -> Dict[str, Any]:
    root = Path(root)
    warnings: List[str] = []
    prod = _track(root, "prod", verify_artifacts, warnings)
    beta = _track(root, "beta", verify_artifacts, warnings)
    index = layout.load_index(root)
    train = layout.read_json(layout.release_train_path(root), required=False)
    retired = [str(v) for v in train.get("retired_versions") or []]

    version_gate = None
    if prod["version"] and beta["version"]:
        version_gate = layout.compare_versions(prod["version"], beta["version"]) < 0
        if not version_gate:
            warnings.append(
                f"prod {prod['version']} 不低于 beta {beta['version']}（晋升候选不成立）"
            )
    same_release = None
    if prod["release_path"] and beta["release_path"]:
        same_release = prod["release_path"] == beta["release_path"]
        if same_release and prod["version"] != beta["version"]:
            warnings.append("两轨指向同一 release 但版本不一致（指针被手工改过？）")

    ancestor = None
    ancestor_error = None
    if prod["git_sha"] and beta["git_sha"]:
        try:
            ancestor = layout.is_ancestor(Path(repo), prod["git_sha"], beta["git_sha"])
            if not ancestor:
                warnings.append("prod sha 不是 beta sha 的祖先（prod 热修未进入候选）")
        except (layout.LayoutError, layout.ExecutionFailure) as exc:
            ancestor_error = str(exc)
            warnings.append(f"祖先检查失败：{exc}")

    observation: Dict[str, Any] = {"days": observation_days}
    beta_record = layout.load_deployment(root, "beta")
    if beta["version"]:
        acceptance = layout.read_json(
            layout.acceptance_file(root, beta["version"]), required=False
        )
        observation["waived"] = bool(acceptance.get("observation_waived"))
        started = beta_record.get("deployed_at") or acceptance.get("approved_at")
        if started:
            try:
                elapsed = datetime.now(timezone.utc) - layout.parse_iso(str(started))
                remaining = timedelta(days=observation_days) - elapsed
                observation.update({
                    "started_at": str(started),
                    "elapsed_days": round(elapsed.total_seconds() / 86400, 2),
                    "remaining_days": round(max(0.0, remaining.total_seconds() / 86400), 2),
                    "ready": observation["waived"] or remaining.total_seconds() <= 0,
                })
            except layout.LayoutError as exc:
                warnings.append(f"观察期起点无法解析：{exc}")
        else:
            observation["ready"] = observation["waived"]

    referenced = sorted(layout.collect_referenced_versions(root))
    missing_dirs = [
        version for version in index["versions"]
        if not layout.release_dir(root, version).is_dir()
    ]
    if missing_dirs:
        warnings.append(
            "台账有版本但目录已清理（仍禁止复用）：" + ", ".join(missing_dirs[:5])
        )
    reused = [version for version in referenced if version in retired]
    if reused:
        warnings.append("已退役版本仍被引用：" + ", ".join(sorted(set(reused))))

    ok = True
    if prod["version"] and beta["version"] and not version_gate:
        ok = False
    if ancestor is False:
        ok = False
    if ancestor_error:
        ok = False
    if verify_artifacts and any(
        track["artifact_verified"] is False for track in (prod, beta)
    ):
        ok = False
    if prod["status"] == "broken" or beta["status"] == "broken":
        ok = False

    return {
        "ok": ok,
        "generated_at": layout.utc_now_iso(),
        "prod": prod,
        "beta": beta,
        "gates": {
            "prod_lt_beta": version_gate,
            "same_release": same_release,
            "merge_base_ancestor": ancestor,
            "ancestor_error": ancestor_error,
        },
        "observation": observation,
        "releases": {
            "indexed": len(index["versions"]),
            "referenced": referenced,
            "retired": retired,
            "missing_dirs": missing_dirs,
        },
        "warnings": warnings,
    }


def _print_track(track: Dict[str, Any]) -> None:
    label = (f"{track['pointer']} -> {track['version']}"
             if track["version"] else f"{track['pointer']} -> （未部署）")
    print(f"  {track['env']:<4} {label}")
    if track["version"]:
        print(f"       release={track['release_path']}")
        print(f"       git_sha={track['git_sha']} "
              f"artifact={str(track['artifact_sha256'])[:16]}…")
        print(f"       schema={track['schema_versions']} "
              f"deployed_at={track['deployed_at']}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BCLRM 发布两轨状态")
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT))
    parser.add_argument("--repo", default=str(PROJECT_ROOT),
                        help="祖先检查所用 git 仓库")
    parser.add_argument("--verify-artifacts", action="store_true",
                        help="重算 payload 哈希（较慢）")
    parser.add_argument("--observation-days", type=int, default=OBSERVATION_DAYS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="门禁模式：不满足返回退出码 2")
    args = parser.parse_args(argv)

    try:
        status = collect_status(
            Path(args.root), Path(args.repo),
            verify_artifacts=args.verify_artifacts,
            observation_days=args.observation_days,
        )
    except (layout.LayoutError, OSError) as exc:
        print(f"[FAIL] 读取发布状态失败：{exc}")
        return 3

    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    else:
        print("== 发布两轨 ==")
        _print_track(status["prod"])
        _print_track(status["beta"])
        gates = status["gates"]
        print("== 门禁 ==")
        print(f"  prod < beta: {gates['prod_lt_beta']}")
        print(f"  同 release : {gates['same_release']}")
        print(f"  祖先关系   : {gates['merge_base_ancestor']}"
              + (f"（{gates['ancestor_error']}）" if gates["ancestor_error"] else ""))
        observation = status["observation"]
        print(f"  观察期     : {observation.get('elapsed_days', 0)}/"
              f"{observation.get('days')} 天，ready={observation.get('ready')}"
              + ("（已豁免）" if observation.get("waived") else ""))
        releases = status["releases"]
        print(f"  release 台账={releases['indexed']} 份，"
              f"仍被引用 {len(releases['referenced'])} 份，"
              f"退役 {len(releases['retired'])} 份")
        for warning in status["warnings"]:
            print(f"[WARN] {warning}")
        print("[ OK ] 状态正常" if status["ok"] else "[FAIL] 门禁未通过")
    return 0 if (status["ok"] or not args.check) else 2


if __name__ == "__main__":
    sys.exit(main())
