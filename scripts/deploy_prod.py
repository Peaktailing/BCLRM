#!/usr/bin/env python3
"""prod 部署与晋升（执行版 4.2.7、5.3、D02/D14/D15/D17）。

顺序固定：预检 → 停服 → 冷备（pre_change）→ 显式迁移 → schema 校验 →
切 current_prod → 启动 → 只读冒烟。任何一步失败：保持停机 → 恢复本次冷备
→ 切回旧 release → 旧版只读冒烟；恢复失败则保持停机并显式告警。

刻意不做的事：不自动迁移（迁移只在这里显式调用 runtime_cli）、不恢复配置包、
不在 beta 指针之外另立版本（D02 同版本同 sha 同制品）。

``--no-systemd`` + ``--skip-http-health`` 供临时环境测试（外部进程管理）；真实
部署不要用。

退出码：0 成功；2 预检失败（未动生产）；3 执行失败（已尝试自动回滚）。
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deploy import release_layout as layout  # noqa: E402
from utils import backup as backup_mod  # noqa: E402

DEFAULT_STOP = ["systemctl", "--user", "stop", "bclrm-prod.service"]
DEFAULT_START = ["systemctl", "--user", "start", "bclrm-prod.service"]
OBSERVATION_DAYS = 3


def _check(checks: List[Dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks.append({"check": name, "ok": bool(ok), "detail": detail})


def _validate_acceptance(root: Path, version: str) -> Dict[str, Any]:
    path = layout.acceptance_file(root, version)
    doc = layout.read_json(path)
    problems = []
    if layout.normalize_version(str(doc.get("version", ""))) != version:
        problems.append("version 不匹配")
    if doc.get("approved") is not True:
        problems.append("approved 必须为 true")
    if not str(doc.get("approver") or "").strip():
        problems.append("缺验收人 approver")
    if str(doc.get("approver_type") or "").lower() in ("ai", "bot", "assistant", "model"):
        problems.append("验收人不能是 AI（需要非 AI 签字记录）")
    if not str(doc.get("signature") or "").strip():
        problems.append("缺签字/签字记录 signature")
    if problems:
        raise layout.LayoutError(f"验收文件 {path} 不满足：" + "; ".join(problems))
    return doc


def _rehearsal_evidence(root: Path, version: str,
                        acceptance: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Path] = []
    explicit = acceptance.get("rehearsal_report")
    if explicit:
        candidates.append(Path(str(explicit)))
    reports_dir = Path(root) / "logs" / "rehearsals"
    if reports_dir.is_dir():
        candidates.extend(sorted(reports_dir.glob("*.json"), reverse=True))
    for path in candidates:
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if doc.get("version") == version and doc.get("ok") is True:
            return {"path": str(path), "finished_at": doc.get("finished_at")}
    raise layout.LayoutError(
        f"没有找到版本 {version} 的成功升级演练报告（logs/rehearsals/*.json）"
    )


def _observation_state(root: Path, acceptance: Dict[str, Any]) -> Dict[str, Any]:
    """D21：beta 观察 3 个自然日；引导期可凭负责人签署的豁免放行。"""
    beta_record = layout.load_deployment(root, "beta")
    started = beta_record.get("deployed_at")
    if started:
        elapsed = datetime.now(timezone.utc) - layout.parse_iso(str(started))
        remaining = timedelta(days=OBSERVATION_DAYS) - elapsed
        if remaining.total_seconds() <= 0:
            return {"ok": True, "detail": f"beta 已观察 {elapsed.total_seconds()/86400:.1f} 天"}
        if acceptance.get("observation_waived") is True:
            return {"ok": True, "waived": True,
                    "detail": "负责人签署了观察期豁免（引导期）"}
        return {"ok": False,
                "detail": f"beta 观察期尚余 {remaining.total_seconds()/3600:.1f} 小时"}
    if acceptance.get("observation_waived") is True:
        return {"ok": True, "waived": True, "detail": "deployments/beta.json 无观察起点，已签署豁免"}
    return {"ok": True, "detail": "beta 尚未部署记录，按引导期处理"}


def _listen_addresses(port: int) -> List[str]:
    try:
        result = subprocess.run(["ss", "-ltn"], capture_output=True, text=True,
                                timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    addresses = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[3].endswith(f":{port}"):
            addresses.append(parts[3])
    return addresses


def _wait_port_closed(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not layout.port_is_listening("127.0.0.1", port):
            return True
        time.sleep(0.5)
    return False


def _run_command(command: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def preflight(args: argparse.Namespace, release: Path,
              doc: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(args.root)
    checks: List[Dict[str, Any]] = []
    context: Dict[str, Any] = {}

    # 1) 制品完整性与 schema map
    actual_sha = layout.payload_sha256(layout.payload_dir(release))
    _check(checks, "artifact_sha256", actual_sha == doc["artifact_sha256"],
           "payload 哈希与 release.json 一致" if actual_sha == doc["artifact_sha256"]
           else f"实际 {actual_sha} != 声明 {doc['artifact_sha256']}")
    _check(checks, "schema_map", all(
        isinstance(doc["schema_versions"].get(name), int) for name in layout.DB_NAMES
    ), f"四库 schema={doc['schema_versions']}")

    # 2) 验收与演练
    try:
        acceptance = _validate_acceptance(root, doc["version"])
        _check(checks, "acceptance", True,
               f"验收人 {acceptance.get('approver')}")
    except layout.LayoutError as exc:
        acceptance = {}
        _check(checks, "acceptance", False, str(exc))
    try:
        rehearsal = _rehearsal_evidence(root, doc["version"], acceptance)
        _check(checks, "rehearsal", True, rehearsal["path"])
    except layout.LayoutError as exc:
        rehearsal = {}
        _check(checks, "rehearsal", False, str(exc))
    observation = _observation_state(root, acceptance)
    _check(checks, "observation", observation["ok"], observation["detail"])
    context["acceptance"] = acceptance
    context["rehearsal"] = rehearsal

    # 2b) 回滚兜底：部署前必须至少有一份能通过校验的快照。
    # 本次部署还会再生成一份冷备，但预检阶段就要证明“现在坏了能退回去”。
    try:
        latest_backup = backup_mod.latest_snapshot(root, "prod")
        _check(checks, "verified_backup", latest_backup is not None,
               str(latest_backup) if latest_backup
               else "prod 没有通过校验的快照（先执行 backup.py 并 verify_backup.py）")
        context["latest_backup"] = str(latest_backup) if latest_backup else None
    except (OSError, ValueError) as exc:
        _check(checks, "verified_backup", False, f"快照校验执行错误：{exc}")

    # 3) 版本与指针（D01/D02）
    prod_release = layout.read_pointer(root, "prod")
    beta_release = layout.read_pointer(root, "beta")
    if not prod_release:
        _check(checks, "current_prod", False,
               "没有 current_prod：首次切换必须走 Stage 2 legacy 专用路径")
    else:
        prod_doc = layout.read_release(prod_release)
        context["prod_doc"] = prod_doc
        same_version = prod_doc["version"] == doc["version"]
        _check(checks, "current_prod", True, str(prod_release))
        _check(checks, "version_increase",
               not same_version and
               layout.compare_versions(prod_doc["version"], doc["version"]) < 0,
               f"prod={prod_doc['version']} target={doc['version']}")
        _check(checks, "prod_reuse", not same_version,
               "目标版本尚未在 prod 部署" if not same_version
               else "版本已部署，禁止复用")
    if beta_release:
        beta_doc = layout.read_release(beta_release)
        _check(checks, "beta_same_version",
               beta_doc["version"] == doc["version"],
               f"beta={beta_doc['version']} target={doc['version']}（D02 同版本晋升）")
        _check(checks, "beta_same_release", beta_release == release,
               f"beta={beta_release} target={release}（必须同一 release 目录）")
        _check(checks, "beta_same_artifact",
               beta_doc["artifact_sha256"] == doc["artifact_sha256"],
               "artifact sha 一致" if beta_doc["artifact_sha256"] == doc["artifact_sha256"]
               else "artifact sha 不一致，禁止晋升")
        context["beta_doc"] = beta_doc
    else:
        _check(checks, "beta_same_version", False, "没有 current_beta，禁止直接生产发布")

    # 4) 祖先检查：prod 热修必须已进入候选
    try:
        prod_doc = context.get("prod_doc")
        if not prod_doc:
            raise layout.LayoutError("缺少 prod release，无法做祖先检查")
        ancestor = layout.is_ancestor(Path(args.repo), prod_doc["git_sha"], doc["git_sha"])
        _check(checks, "merge_base_ancestor", ancestor,
               f"{prod_doc['git_sha'][:8]} 是 {doc['git_sha'][:8]} 的祖先"
               if ancestor else "prod sha 不是候选 sha 的祖先（prod 热修未进候选）")
    except (layout.LayoutError, layout.ExecutionFailure) as exc:
        _check(checks, "merge_base_ancestor", False, str(exc))

    # 5) 台账与磁盘
    index = layout.load_index(root)
    _check(checks, "releases_index", doc["version"] in index["versions"],
           "release 已登记" if doc["version"] in index["versions"] else "release 未登记")
    free = layout.disk_free_gib(root)
    _check(checks, "disk_free", free >= args.min_free_gib,
           f"可用 {free:.1f} GiB（阈值 {args.min_free_gib}）")
    if not args.no_systemd and not args.skip_http_health:
        addresses = _listen_addresses(args.port)
        if addresses:
            _check(checks, "port_before_stop", False,
                   f"部署前 {args.port} 仍在监听：{addresses}")
        else:
            _check(checks, "port_before_stop", True, f"{args.port} 当前未监听")
    else:
        _check(checks, "port_before_stop", True, "--no-systemd：外部进程管理，跳过")
    return {"checks": checks, "ok": all(item["ok"] for item in checks),
            "context": context}


def _record(root: Path, env: str, record: Dict[str, Any]) -> None:
    layout.save_deployment(root, env, record)


def fail_and_rollback(
    *, args: argparse.Namespace, release: Path, doc: Dict[str, Any],
    old_release: Optional[Path], old_doc: Optional[Dict[str, Any]],
    snapshot: Optional[Path], backup_manifest: Optional[Dict[str, Any]],
    acceptance: Dict[str, Any], rehearsal: Dict[str, Any],
    error: str, service_was_started: bool,
) -> int:
    """停机 → 恢复本次冷备 → 切回旧 release → 旧版只读冒烟。"""
    root = Path(args.root)
    outcome: Dict[str, Any] = {"error": error, "restore_ok": False,
                               "switch_back_ok": False, "smoke_ok": False}
    print(f"[FAIL] {error}")
    # 先确保新进程不在运行（可能启动到一半），再恢复数据
    if not args.no_systemd:
        _run_command(args.stop_command_list)
    if snapshot is None:
        print("[CRIT] 没有可用冷备，保持停机，请人工处理")
        outcome["critical"] = "no_snapshot"
    else:
        try:
            backup_mod.restore_snapshot(snapshot, layout.data_dir(root, "prod"),
                                        replace=True)
            outcome["restore_ok"] = True
            print(f"[ OK ] 已恢复冷备 {snapshot}")
        except (backup_mod.BackupVerificationError, backup_mod.BackupError,
                layout.LayoutError, OSError) as exc:
            outcome["critical"] = f"恢复失败：{exc}"
            print(f"[CRIT] 恢复冷备失败：{exc}；保持停机并保留现场")
    if old_release is not None:
        try:
            layout.switch_pointer(root, "prod", old_release.name)
            outcome["switch_back_ok"] = True
            print(f"[ OK ] current_prod 已切回 {old_release.name}")
        except (layout.LayoutError, OSError) as exc:
            outcome["critical_switch"] = str(exc)
            print(f"[CRIT] 指针回切失败：{exc}")
        if not args.no_systemd:
            _run_command(args.start_command_list)
            if not args.skip_http_health:
                health = layout.wait_http_ok(
                    args.health_url, timeout=args.health_timeout
                )
                outcome["health_back"] = health
        if outcome["restore_ok"] and old_doc is not None:
            smoke = layout.run_runtime_cli(old_release, "smoke", "prod",
                                           layout.data_dir(root, "prod"))
            outcome["smoke_ok"] = smoke.returncode == 0
            if not outcome["smoke_ok"]:
                print("[CRIT] 旧版只读冒烟失败，服务不得开放")
    _record(root, "prod", {
        "env": "prod",
        "status": "rolled_back_failed_deploy",
        "failed_version": doc["version"],
        "release_path": str(old_release) if old_release else None,
        "version": old_doc["version"] if old_doc else None,
        "previous": {
            "version": doc["version"], "release_path": str(release),
            "git_sha": doc["git_sha"],
        },
        "backup": {
            "path": str(snapshot) if snapshot else None,
            "id": snapshot.name if snapshot else None,
            "mode": "cold",
        },
        "acceptance": {"approver": acceptance.get("approver")},
        "rehearsal": rehearsal,
        "failure": outcome,
    })
    layout.update_index_status(root, doc["version"], "failed")
    print("[FAIL] 部署失败，已按规程尝试恢复；详见 deployments/prod.json")
    return 3


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BCLRM prod 部署/晋升")
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT))
    parser.add_argument("--repo", default=str(PROJECT_ROOT),
                        help="用于 merge-base 祖先检查的 git 仓库")
    parser.add_argument("--version", help="目标版本")
    parser.add_argument("--release", type=Path, help="目标 release 目录")
    parser.add_argument("--execute", action="store_true",
                        help="真正执行；缺省只做预检")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--health-url", default="http://127.0.0.1:8501/_stcore/health")
    parser.add_argument("--health-timeout", type=float, default=90.0)
    parser.add_argument("--stop-command", default=None)
    parser.add_argument("--start-command", default=None)
    parser.add_argument("--no-systemd", action="store_true",
                        help="测试：外部管理进程，工具不停/起服务")
    parser.add_argument("--skip-http-health", action="store_true",
                        help="测试：跳过 HTTP 健康检查")
    parser.add_argument("--min-free-gib", type=float, default=5.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if bool(args.version) == bool(args.release):
        parser.error("--version 与 --release 必须二选一")
    root = Path(args.root)
    release = args.release or layout.release_dir(root, args.version)
    args.stop_command_list = (shlex.split(args.stop_command)
                              if args.stop_command else DEFAULT_STOP)
    args.start_command_list = (shlex.split(args.start_command)
                               if args.start_command else DEFAULT_START)

    try:
        doc = layout.read_release(release)
        if args.version and layout.normalize_version(args.version) != doc["version"]:
            raise layout.LayoutError("--version 与 release.json 不一致")
    except (layout.LayoutError, OSError) as exc:
        print(f"[FAIL] 目标 release 不可用：{exc}")
        return 2

    try:
        pre = preflight(args, release, doc)
    except (layout.LayoutError, layout.ExecutionFailure, OSError) as exc:
        print(f"[FAIL] 预检执行错误：{exc}")
        return 2

    if args.json:
        print(json.dumps({"preflight": pre, "execute": args.execute},
                         ensure_ascii=False, indent=2, default=str))
    else:
        for item in pre["checks"]:
            mark = "OK  " if item["ok"] else "FAIL"
            print(f"[{mark}] {item['check']}: {item['detail']}")
    if not pre["ok"]:
        print("[FAIL] 预检未通过，生产未被改动")
        return 2
    if not args.execute:
        print(f"[DRY-RUN] 预检通过：将停服 → 冷备 → 迁移到 {doc['version']} → "
              "切 current_prod → 启动 → 只读冒烟")
        return 0

    context = pre["context"]
    acceptance = context.get("acceptance") or {}
    rehearsal = context.get("rehearsal") or {}
    old_release = layout.read_pointer(root, "prod")
    old_doc = context.get("prod_doc")
    snapshot: Optional[Path] = None
    service_stopped = False
    service_started = False

    # 1) 停服（真实部署）；测试模式假定外部已停
    if not args.no_systemd:
        result = _run_command(args.stop_command_list)
        if result.returncode != 0:
            print(f"[FAIL] 停服失败：{result.stderr.strip()}")
            return 3
        if not _wait_port_closed(args.port):
            print(f"[FAIL] {args.port} 仍在监听，停止部署（生产未改数据）")
            _run_command(args.start_command_list)
            return 3
        service_stopped = True
        print(f"[ OK ] 服务已停，{args.port} 已释放")

    # 2) 冷备
    try:
        backup_result = backup_mod.create_backup(
            root, "prod", "pre_change", mode="cold", source="deploy",
            label=f"before {doc['version']}", service_stopped=True,
            min_free_gib=args.min_free_gib,
        )
        snapshot = Path(backup_result["snapshot"])
        backup_manifest = backup_result["manifest"]
        layout.write_json_atomic(
            layout.backups_dir(root, "prod") / "last_verified.json",
            {"snapshot": snapshot.name, "verified_at": layout.utc_now_iso(),
             "snapshot_path": str(snapshot)},
        )
        print(f"[ OK ] 冷备 {snapshot}")
    except (backup_mod.BackupError, backup_mod.BackupVerificationError,
            layout.LayoutError, OSError) as exc:
        print(f"[FAIL] 冷备失败，部署终止：{exc}")
        if not args.no_systemd:
            _run_command(args.start_command_list)
        # 即使还没切换指针，也落一条失败记录：生产状态必须可审计，
        # 不能让 release_status 误以为这是一次“未开始”的部署。
        _record(root, "prod", {
            "env": "prod",
            "status": "failed_pre_change",
            "failed_version": doc["version"],
            "version": old_doc["version"] if old_doc else None,
            "release_path": str(old_release) if old_release else None,
            "previous": {
                "version": doc["version"], "release_path": str(release),
                "git_sha": doc["git_sha"],
            },
            "backup": {"path": None, "id": None, "mode": "cold"},
            "acceptance": {"approver": acceptance.get("approver")},
            "rehearsal": rehearsal,
            "failure": {"stage": "cold_backup", "error": str(exc)},
        })
        layout.update_index_status(root, doc["version"], "failed")
        return 3

    def abort(message: str) -> int:
        return fail_and_rollback(
            args=args, release=release, doc=doc,
            old_release=old_release, old_doc=old_doc,
            snapshot=snapshot, backup_manifest=backup_manifest,
            acceptance=acceptance, rehearsal=rehearsal,
            error=message, service_was_started=service_started,
        )

    # 3) 显式迁移 + 校验（D14/D15）
    migrate = layout.run_runtime_cli(release, "migrate", "prod",
                                     layout.data_dir(root, "prod"))
    print(migrate.stdout.strip())
    if migrate.returncode != 0:
        return abort(f"显式迁移失败（rc={migrate.returncode}）：{migrate.stderr.strip()[:300]}")
    check = layout.run_runtime_cli(release, "check", "prod",
                                   layout.data_dir(root, "prod"))
    if check.returncode != 0:
        return abort(f"迁移后 schema 校验失败：{check.stderr.strip()[:300] or check.stdout.strip()[:300]}")
    print("[ OK ] 迁移与 schema 校验通过")

    # 4) 切指针
    try:
        layout.switch_pointer(root, "prod", doc["version"])
        print(f"[ OK ] current_prod -> releases/{doc['version']}")
    except (layout.LayoutError, OSError) as exc:
        return abort(f"切换指针失败：{exc}")

    # 5) 启动 + 健康检查 + 只读冒烟
    try:
        if not args.no_systemd:
            result = _run_command(args.start_command_list)
            if result.returncode != 0:
                return abort(f"启动服务失败：{result.stderr.strip()}")
            service_started = True
            if not args.skip_http_health:
                if not layout.wait_http_ok(args.health_url, timeout=args.health_timeout):
                    return abort("服务未通过健康检查")
                addresses = _listen_addresses(args.port)
                if addresses and not all(
                    address.startswith("127.0.0.1:") for address in addresses
                ):
                    return abort(f"监听地址不是 127.0.0.1：{addresses}")
        smoke = layout.run_runtime_cli(release, "smoke", "prod",
                                       layout.data_dir(root, "prod"))
        if smoke.returncode != 0:
            return abort(f"只读冒烟失败：{smoke.stderr.strip()[:300] or smoke.stdout.strip()[:300]}")
    except (layout.LayoutError, layout.ExecutionFailure, OSError) as exc:
        return abort(f"启动/冒烟异常：{exc}")

    now = datetime.now(timezone.utc)
    deployment = {
        "env": "prod",
        "status": "deployed",
        "version": doc["version"],
        "release_path": str(release),
        "git_sha": doc["git_sha"],
        "artifact_sha256": doc["artifact_sha256"],
        "schema_versions": doc["schema_versions"],
        "deployed_at": now.isoformat(timespec="seconds"),
        "previous": {
            "version": old_doc["version"] if old_doc else None,
            "release_path": str(old_release) if old_release else None,
            "git_sha": old_doc["git_sha"] if old_doc else None,
        },
        "backup": {
            "path": str(snapshot), "id": snapshot.name, "mode": "cold",
            "kind": "pre_change",
            "verified_at": layout.utc_now_iso(),
        },
        "rollback_snapshot": str(snapshot),
        "rollback_release": old_doc["version"] if old_doc else None,
        "acceptance": {"approver": acceptance.get("approver"),
                       "signature": acceptance.get("signature")},
        "rehearsal": rehearsal,
        "observation": {
            "days": OBSERVATION_DAYS,
            "started_at": now.isoformat(timespec="seconds"),
        },
        "service_stopped_declared": service_stopped or args.no_systemd,
    }
    _record(root, "prod", deployment)
    layout.update_index_status(root, doc["version"], "deployed")
    if args.json:
        print(json.dumps({"ok": True, "deployment": deployment},
                         ensure_ascii=False, indent=2, default=str))
    else:
        print(f"[ OK ] prod 已部署 {doc['version']}（只读冒烟通过）")
        print(f"[INFO] 回滚快照 {snapshot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
