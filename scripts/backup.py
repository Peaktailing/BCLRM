#!/usr/bin/env python3
"""在线/冷备份 CLI（执行版 4.3/4.4/4.5）。

- 热备：SQLite backup API 先库后附件，附件索引引用缺失立即失败；
- 冷备：必须显式 ``--service-stopped``，工具不替你猜服务是否停了；
- ``--copy-latest-from daily``：半月/年度档从最近一份已验证快照复制；
- ``--second-copy-root``：复制到同机第二副本并重新校验，失败显式退出。

默认执行备份（备份本身不破坏现场）；``--dry-run`` 只打印计划。

用法：
    python scripts/backup.py --env prod --kind daily --mode hot
    python scripts/backup.py --env prod --kind pre_change --mode cold --service-stopped
    python scripts/backup.py --env prod --kind semimonthly --copy-latest-from daily

退出码：0 成功；2 预检失败；3 执行失败。
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


def _record_cron_status(root: Path, key: str, payload: dict) -> None:
    """备份结果落到 logs/cron_status.json（系统设置页展示最近成功/失败）。"""
    path = Path(root) / "logs" / "cron_status.json"
    try:
        data = layout.read_json(path, required=False)
    except layout.LayoutError:
        data = {}
    data.setdefault("schema_version", 1)
    data[key] = payload
    layout.write_json_atomic(path, data)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BCLRM 四库+附件快照备份")
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT))
    parser.add_argument("--env", required=True, choices=("prod", "beta", "dev"))
    parser.add_argument("--kind", default="daily", choices=backup_mod.BACKUP_KINDS)
    parser.add_argument("--mode", default="hot", choices=("hot", "cold"))
    parser.add_argument("--service-stopped", action="store_true",
                        help="冷备/一致性承诺：调用方已确认服务停止")
    parser.add_argument("--source", default="manual",
                        help="来源标记：manual / timer / deploy / reset")
    parser.add_argument("--label", default="", help="备注（不含秘密）")
    parser.add_argument("--copy-latest-from", choices=backup_mod.BACKUP_KINDS,
                        help="从指定类型的最近已验证快照复制成本次类型")
    parser.add_argument("--second-copy-root", type=Path,
                        help="同机第二副本根（跨盘只复制并重新校验）")
    parser.add_argument("--min-free-gib", type=float, default=backup_mod.MIN_FREE_GIB,
                        help="低于该可用空间拒绝备份（默认 5）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划")
    parser.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    args = parser.parse_args(argv)

    root = Path(args.root)
    try:
        if args.mode == "cold" and not args.service_stopped:
            raise layout.LayoutError(
                "冷备必须确认服务已停：加 --service-stopped（升级前冷备不得热做）"
            )
        data_root = layout.data_dir(root, args.env)
        if not (data_root / "db").is_dir():
            raise layout.LayoutError(f"数据根未初始化：{data_root}")
        if args.copy_latest_from == args.kind:
            raise layout.LayoutError("--copy-latest-from 不能与目标类型相同")
        source_snapshot = None
        if args.copy_latest_from:
            source_snapshot = backup_mod.latest_snapshot(
                root, args.env, kind=args.copy_latest_from
            )
            if source_snapshot is None:
                raise layout.LayoutError(
                    f"没有可用的已验证 {args.copy_latest_from} 快照可供复制"
                )
    except layout.LayoutError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[FAIL] 预检失败：{exc}")
        return 2

    if args.dry_run:
        plan = {
            "action": "copy" if source_snapshot else "backup",
            "root": str(root),
            "env": args.env,
            "kind": args.kind,
            "mode": args.mode,
            "source_snapshot": str(source_snapshot) if source_snapshot else None,
            "second_copy_root": str(args.second_copy_root) if args.second_copy_root else None,
        }
        if args.json:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
        else:
            print("[DRY-RUN] " + json.dumps(plan, ensure_ascii=False))
        return 0

    try:
        if source_snapshot:
            result = backup_mod.clone_snapshot(
                source_snapshot, root, args.env, args.kind, origin=args.source
            )
        else:
            result = backup_mod.create_backup(
                root, args.env, args.kind, mode=args.mode,
                source=args.source, label=args.label,
                service_stopped=args.service_stopped,
                min_free_gib=args.min_free_gib,
            )
        snapshot = Path(result["snapshot"])
        second = None
        if args.second_copy_root:
            second = backup_mod.copy_to_second_location(
                snapshot, args.second_copy_root, args.env
            )
        # 只有本工具刚校验过，才更新“最近验证快照”指针
        layout.write_json_atomic(
            layout.backups_dir(root, args.env) / "last_verified.json",
            {"snapshot": snapshot.name, "verified_at": layout.utc_now_iso(),
             "snapshot_path": str(snapshot)},
        )
        _record_cron_status(root, "backup", {
            "ok": True, "at": layout.utc_now_iso(),
            "env": args.env, "kind": args.kind, "mode": args.mode,
            "snapshot": str(snapshot),
            "second_copy": second["target"] if second else None,
        })
    except layout.LayoutError as exc:
        print(f"[FAIL] 预检失败：{exc}")
        return 2
    except (backup_mod.BackupError, backup_mod.BackupVerificationError,
            OSError) as exc:
        _record_cron_status(root, "backup", {
            "ok": False, "at": layout.utc_now_iso(),
            "env": args.env, "kind": args.kind, "mode": args.mode,
            "error": str(exc)[:500],
        })
        print(f"[FAIL] 备份失败：{exc}")
        return 3

    summary = {
        "ok": True,
        "snapshot": str(snapshot),
        "kind": args.kind,
        "mode": args.mode,
        "version": result["manifest"].get("version"),
        "schema_versions": result["manifest"].get("schema_versions"),
        "attachments_files": result["manifest"]["attachments"]["file_count"],
        "second_copy": second["target"] if second else None,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"[ OK ] 快照 {snapshot}")
        print(f"[INFO] kind={args.kind} mode={args.mode} "
              f"version={summary['version']} "
              f"attachments={summary['attachments_files']}")
        if second:
            print(f"[ OK ] 第二副本 {second['target']} 已重新校验")
    return 0


if __name__ == "__main__":
    sys.exit(main())
