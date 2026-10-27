#!/usr/bin/env python3
"""显式恢复快照到目标目录（执行版 4.4）。

硬约束（刻意不做“通用 --force”）：

- ``--target`` 必须是绝对路径，且位于 ``<root>/data/<env>`` 之内；
- prod 恢复额外要求 ``--confirm-prod`` 与 ``--service-stopped`` 两个开关；
- 目标已存在时必须 ``--replace``，旧目录改名保留现场而非直接删除；
- 默认 dry-run，只有 ``--execute`` 才落盘。

用法：
    python scripts/restore.py --snapshot ... --env beta --target /.../data/beta/rehearsal --execute
    python scripts/restore.py --snapshot ... --env prod --target /home/biochm/BCLRM/data/prod \
        --confirm-prod --service-stopped --replace --execute

退出码：0 成功；2 预检/校验失败；3 执行失败。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deploy import release_layout as layout  # noqa: E402
from utils import backup as backup_mod  # noqa: E402


def _has_payload(target: Path) -> bool:
    return (target / "db").is_dir() or (target / "attachments").is_dir()


def validate_target(root: Path, env: str, target: Path) -> Path:
    if not target.is_absolute():
        raise layout.LayoutError(f"--target 必须是绝对路径：{target}")
    resolved = target.resolve()
    allowed = layout.data_dir(root, env).resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise layout.LayoutError(
            f"恢复目标必须位于 {allowed} 内，实际 {resolved}"
        )
    if resolved == Path(root).resolve():
        raise layout.LayoutError("拒绝把部署根作为恢复目标")
    return resolved


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="恢复 BCLRM 快照到显式目标")
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT))
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--env", required=True, choices=("prod", "beta", "dev"))
    parser.add_argument("--target", required=True, help="绝对目标目录（位于 data/<env>）")
    parser.add_argument("--confirm-prod", action="store_true",
                        help="prod 恢复的显式人工确认")
    parser.add_argument("--service-stopped", action="store_true",
                        help="确认服务已停止（prod 必填）")
    parser.add_argument("--replace", action="store_true",
                        help="目标已有 db/attachments 时允许替换（旧目录保留改名）")
    parser.add_argument("--with-config", action="store_true",
                        help="同时恢复配置包（仅整机灾难重建，显式开启）")
    parser.add_argument("--allow-cross-env", action="store_true",
                        help="允许 prod 快照恢复到非 prod 环境（beta 重建用）")
    parser.add_argument("--execute", action="store_true",
                        help="真正落盘；缺省只做 dry-run")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root)
    try:
        target = validate_target(root, args.env, Path(args.target))
        if args.env == "prod":
            if not args.confirm_prod:
                raise layout.LayoutError("prod 恢复必须加 --confirm-prod")
            if not args.service_stopped:
                raise layout.LayoutError("prod 恢复必须加 --service-stopped")
        if target.exists() and _has_payload(target) and not args.replace:
            raise layout.LayoutError(
                f"目标已有数据，必须显式 --replace 才允许覆盖：{target}"
            )
        report = backup_mod.verify_snapshot(Path(args.snapshot))
        if not report["ok"]:
            raise backup_mod.BackupVerificationError(
                "快照校验失败：" + "; ".join(report["errors"][:5])
            )
        source_env = report["manifest"]["source"]["env"]
        if args.env == "prod" and source_env != "prod" and not args.allow_cross_env:
            raise layout.LayoutError(
                f"拒绝把 {source_env} 快照恢复到 prod（除非 --allow-cross-env）"
            )
    except layout.LayoutError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[FAIL] 预检失败：{exc}")
        return 2
    except backup_mod.BackupVerificationError as exc:
        print(f"[FAIL] 校验失败：{exc}")
        return 2
    except OSError as exc:
        print(f"[FAIL] 执行错误：{exc}")
        return 3

    plan = {
        "snapshot": str(Path(args.snapshot)),
        "target": str(target),
        "env": args.env,
        "replace": args.replace or not target.exists(),
        "with_config": args.with_config,
        "version": report["manifest"].get("version"),
        "execute": args.execute,
    }
    if not args.execute:
        if args.json:
            print(json.dumps({"ok": True, "dry_run": True, "plan": plan},
                             ensure_ascii=False, indent=2))
        else:
            print("[DRY-RUN] " + json.dumps(plan, ensure_ascii=False))
            print("[INFO] 快照校验通过；加 --execute 才会落盘")
        return 0

    try:
        result = backup_mod.restore_snapshot(
            Path(args.snapshot), target, replace=args.replace,
            include_config=args.with_config,
            config_root=root if args.with_config else None,
        )
    except (backup_mod.BackupVerificationError, backup_mod.BackupError,
            layout.LayoutError, OSError) as exc:
        print(f"[FAIL] 恢复失败：{exc}")
        return 3

    if args.json:
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2,
                         default=str))
    else:
        print(f"[ OK ] 已恢复 {result['snapshot']} -> {result['target']}")
        if result["replaced_from"]:
            print(f"[INFO] 原目录保留为 {result['replaced_from']}")
        print(f"[INFO] version={result['version']} "
              f"schema={result['schema_versions']} "
              f"attachments={result['attachments_files']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
