#!/usr/bin/env python3
"""prod 回滚（执行版 5.3、D17）。

常规回滚 = 停服 + 恢复升级前数据快照 + 切回匹配的旧 release；不执行 down
migration，不回滚共享发布元数据（deployments/release_train 追加记录而非改写）。

首次上线的 legacy 回滚只提供**占位接口**：``--legacy <dir>`` 要求目录与
``legacy_manifest.json`` 已由 Stage 2 创建，本工具只实现“停新版 → 恢复数据到
legacy 目录 → 启动 legacy unit”的逻辑，绝不创建 legacy 目录。

退出码：0 成功；2 预检失败（未动生产）；3 执行失败。
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deploy import release_layout as layout  # noqa: E402
from utils import backup as backup_mod  # noqa: E402

DEFAULT_STOP = ["systemctl", "--user", "stop", "bclrm-prod.service"]
DEFAULT_START = ["systemctl", "--user", "start", "bclrm-prod.service"]
DEFAULT_LEGACY_STOP = ["systemctl", "--user", "stop", "bclrm-prod-legacy.service"]
DEFAULT_LEGACY_START = ["systemctl", "--user", "start", "bclrm-prod-legacy.service"]


def _run(command: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=120)


def _wait_closed(port: int, timeout: float = 30.0) -> bool:
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not layout.port_is_listening("127.0.0.1", port):
            return True
        time.sleep(0.5)
    return False


def _deployment_rollback_plan(root: Path) -> Dict[str, Any]:
    record = layout.load_deployment(root, "prod")
    target_version = record.get("rollback_release")
    if not target_version and isinstance(record.get("previous"), dict):
        target_version = record["previous"].get("version")
    snapshot = record.get("rollback_snapshot")
    if not snapshot and isinstance(record.get("backup"), dict):
        snapshot = record["backup"].get("path")
    return {
        "version": target_version,
        "snapshot": snapshot,
        "current_version": record.get("version"),
        "record": record,
    }


def _legacy_preflight(root: Path, legacy: Path) -> Dict[str, Any]:
    legacy = Path(legacy)
    if not legacy.is_absolute():
        raise layout.LayoutError("--legacy 必须是绝对路径")
    legacy = legacy.resolve()
    expected = (Path(root) / "legacy").resolve()
    if legacy != expected and expected not in legacy.parents:
        raise layout.LayoutError(f"legacy 目录必须位于 {expected} 下")
    if not legacy.is_dir():
        raise layout.LayoutError(
            f"legacy 目录不存在：{legacy}（Stage 2 才创建，本工具不代建）"
        )
    manifest = legacy / "legacy_manifest.json"
    if not manifest.is_file():
        raise layout.LayoutError(f"legacy 缺少 legacy_manifest.json：{manifest}")
    doc = layout.read_json(manifest)
    for key in ("git_sha", "created_at", "source_path"):
        if not doc.get(key):
            raise layout.LayoutError(f"legacy manifest 缺字段：{key}")
    return {"legacy": legacy, "manifest": doc}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BCLRM prod 回滚")
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT))
    parser.add_argument("--to", help="回滚目标版本（默认部署记录的 previous）")
    parser.add_argument("--snapshot", help="回滚快照（默认部署记录的 rollback_snapshot）")
    parser.add_argument("--legacy", type=Path,
                        help="首次上线 legacy 目录（占位接口，目录由 Stage 2 创建）")
    parser.add_argument("--confirm-prod", action="store_true")
    parser.add_argument("--service-stopped", action="store_true",
                        help="确认允许工具停服执行回滚")
    parser.add_argument("--execute", action="store_true", help="缺省 dry-run")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--health-url", default="http://127.0.0.1:8501/_stcore/health")
    parser.add_argument("--health-timeout", type=float, default=90.0)
    parser.add_argument("--no-systemd", action="store_true",
                        help="测试：外部管理进程")
    parser.add_argument("--skip-http-health", action="store_true")
    parser.add_argument("--stop-command", default=None)
    parser.add_argument("--start-command", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root)
    stop_command = shlex.split(args.stop_command) if args.stop_command else DEFAULT_STOP
    start_command = shlex.split(args.start_command) if args.start_command else DEFAULT_START
    plan = _deployment_rollback_plan(root)

    try:
        if not args.execute:
            pass
        elif not args.confirm_prod:
            raise layout.LayoutError("prod 回滚必须加 --confirm-prod")
        elif not args.service_stopped:
            raise layout.LayoutError("prod 回滚必须加 --service-stopped（工具会停服）")

        if args.legacy:
            legacy_info = _legacy_preflight(root, args.legacy)
            snapshot_value = args.snapshot or plan["snapshot"]
            if not snapshot_value:
                raise layout.LayoutError("legacy 回滚需要 --snapshot（部署记录里没有回滚点）")
            snapshot = Path(snapshot_value)
            verify = backup_mod.verify_snapshot(snapshot)
            if not verify["ok"]:
                raise backup_mod.BackupVerificationError(
                    "回滚快照校验失败：" + "; ".join(verify["errors"][:5])
                )
            mode = "legacy"
            target_version = None
            release = None
        else:
            legacy_info = {}
            target_version = args.to or plan["version"]
            if not target_version:
                raise layout.LayoutError("部署记录没有 previous/rollback_release，必须 --to")
            target_version = layout.normalize_version(target_version)
            release = layout.release_dir(root, target_version)
            if not release.is_dir():
                raise layout.LayoutError(f"回滚目标 release 不存在：{release}")
            layout.read_release(release)
            snapshot_value = args.snapshot or plan["snapshot"]
            if not snapshot_value:
                raise layout.LayoutError("没有回滚快照：部署记录缺 rollback_snapshot")
            snapshot = Path(snapshot_value)
            verify = backup_mod.verify_snapshot(snapshot)
            if not verify["ok"]:
                raise backup_mod.BackupVerificationError(
                    "回滚快照校验失败：" + "; ".join(verify["errors"][:5])
                )
            if verify["manifest"]["source"]["env"] != "prod":
                raise layout.LayoutError("prod 回滚只接受 prod 快照")
            mode = "release"
    except layout.LayoutError as exc:
        print(f"[FAIL] 预检失败：{exc}")
        return 2
    except backup_mod.BackupVerificationError as exc:
        print(f"[FAIL] 快照校验失败：{exc}")
        return 2

    summary_plan = {
        "mode": mode,
        "to_version": target_version,
        "legacy": str(legacy_info.get("legacy")) if legacy_info else None,
        "snapshot": str(snapshot),
        "current_version": plan["current_version"],
        "execute": args.execute,
    }
    if not args.execute:
        if args.json:
            print(json.dumps({"ok": True, "dry_run": True, "plan": summary_plan},
                             ensure_ascii=False, indent=2))
        else:
            print("[DRY-RUN] " + json.dumps(summary_plan, ensure_ascii=False))
            print("[INFO] 加 --confirm-prod --service-stopped --execute 才会执行")
        return 0

    # 停服
    if not args.no_systemd:
        result = _run(stop_command)
        if result.returncode != 0:
            print(f"[FAIL] 停新版服务失败：{result.stderr.strip()}")
            return 3
        if not _wait_closed(args.port):
            print(f"[FAIL] {args.port} 仍在监听，回滚中止（未改数据）")
            return 3
    print("[ OK ] 新版服务已停")

    try:
        if mode == "legacy":
            target_dir = Path(legacy_info["legacy"])
            # 只替换 legacy 目录里的 db/ 与 attachments/，保留其应用代码
            restored = backup_mod.restore_snapshot(
                snapshot, target_dir, replace=True, merge=True
            )
            if not args.no_systemd:
                start = _run(DEFAULT_LEGACY_START)
                if start.returncode != 0:
                    raise layout.ExecutionFailure(
                        f"legacy 服务启动失败：{start.stderr.strip()}"
                    )
                if not args.skip_http_health and not layout.wait_http_ok(
                    args.health_url, timeout=args.health_timeout
                ):
                    raise layout.ExecutionFailure("legacy 服务未通过健康检查")
            record = {
                "env": "prod",
                "status": "legacy_rolled_back",
                "mode": "legacy",
                "legacy_path": str(target_dir),
                "legacy_git_sha": legacy_info["manifest"].get("git_sha"),
                "backup": {"path": str(snapshot), "id": snapshot.name},
                "version": plan["current_version"],
                "rolled_back_at": layout.utc_now_iso(),
                "failed_version": plan["current_version"],
            }
        else:
            restored = backup_mod.restore_snapshot(
                snapshot, layout.data_dir(root, "prod"), replace=True
            )
            layout.switch_pointer(root, "prod", target_version)
            if not args.no_systemd:
                start = _run(start_command)
                if start.returncode != 0:
                    raise layout.ExecutionFailure(f"旧版启动失败：{start.stderr.strip()}")
                if not args.skip_http_health and not layout.wait_http_ok(
                    args.health_url, timeout=args.health_timeout
                ):
                    raise layout.ExecutionFailure("旧版服务未通过健康检查")
            smoke = layout.run_runtime_cli(release, "smoke", "prod",
                                           layout.data_dir(root, "prod"))
            if smoke.returncode != 0:
                raise layout.ExecutionFailure("回滚后只读冒烟失败，服务不得开放")
            record = {
                "env": "prod",
                "status": "rolled_back",
                "mode": "release",
                "version": target_version,
                "release_path": str(release),
                "git_sha": layout.read_release(release)["git_sha"],
                "rolled_back_at": layout.utc_now_iso(),
                "failed_version": plan["current_version"],
                "backup": {"path": str(snapshot), "id": snapshot.name},
                "rollback_snapshot": str(snapshot),
            }
    except (layout.LayoutError, layout.ExecutionFailure,
            backup_mod.BackupVerificationError, backup_mod.BackupError,
            OSError) as exc:
        print(f"[CRIT] 回滚失败：{exc}；服务保持停机，保留现场并立即告警")
        layout.save_deployment(root, "prod", {
            "env": "prod",
            "status": "rollback_failed",
            "version": plan["current_version"],
            "failed_target": target_version or "legacy",
            "failed_at": layout.utc_now_iso(),
            "backup": {"path": str(snapshot), "id": snapshot.name},
            "error": str(exc)[:500],
        })
        return 3

    layout.save_deployment(root, "prod", record)
    if target_version:
        layout.update_index_status(root, target_version, "deployed")
    if plan["current_version"]:
        layout.update_index_status(root, plan["current_version"], "rolled_back")
    if args.json:
        print(json.dumps({"ok": True, "rolled_back": record, "restored": restored},
                         ensure_ascii=False, indent=2, default=str))
    else:
        print(f"[ OK ] 已回滚（{mode}）：{target_version or 'legacy'}，"
              f"快照 {snapshot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
