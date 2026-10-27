#!/usr/bin/env python3
"""快照只读校验（执行版 4.4）。

检查 manifest 自洽、逐文件哈希、四库完整性/user_version、附件索引引用。
全程只读：不解包到快照目录、不建临时库、不修改快照 mtime 之外的任何内容。

用法：
    python scripts/verify_backup.py --snapshot /home/biochm/BCLRM/backups/prod/daily/xxx
    python scripts/verify_backup.py --root /home/biochm/BCLRM --env prod --latest

退出码：0 通过；2 校验不通过；3 执行错误。
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


def resolve_snapshot(args: argparse.Namespace) -> Path:
    explicit = args.snapshot_opt or args.snapshot
    if explicit:
        return Path(explicit)
    if not args.env:
        raise layout.LayoutError("未给 --snapshot 时必须提供 --env 以定位最新快照")
    if args.name:
        for kind in backup_mod.BACKUP_KINDS:
            candidate = layout.backups_dir(Path(args.root), args.env) / kind / args.name
            if candidate.is_dir():
                return candidate
        raise layout.LayoutError(f"找不到快照：{args.name}")
    latest = backup_mod.latest_snapshot(
        Path(args.root), args.env, kind=args.kind, require_verified=False
    )
    if latest is None:
        raise layout.LayoutError("该环境下没有快照")
    return latest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="只读校验一份 BCLRM 快照")
    parser.add_argument("snapshot", nargs="?", help="快照目录")
    parser.add_argument("--snapshot", dest="snapshot_opt",
                        help="快照目录（与位置参数等价，便于脚本统一）")
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT))
    parser.add_argument("--env", choices=("prod", "beta", "dev"),
                        help="配合 --latest/--name 定位")
    parser.add_argument("--kind", choices=backup_mod.BACKUP_KINDS,
                        help="配合 --latest 限定类型")
    parser.add_argument("--name", help="快照目录名")
    parser.add_argument("--latest", action="store_true",
                        help="校验该环境最新快照（可与 --kind 组合）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not (args.snapshot or args.snapshot_opt) and not args.latest and not args.name:
        parser.error("需要 snapshot 位置参数，或 --latest / --name")

    try:
        snapshot = resolve_snapshot(args)
    except layout.LayoutError as exc:
        print(f"[FAIL] 无法定位快照：{exc}")
        return 2

    try:
        report = backup_mod.verify_snapshot(snapshot)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] 校验执行错误：{exc}")
        return 3

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2,
                         default=str))
    else:
        manifest = report.get("manifest") or {}
        print(f"[INFO] snapshot={report['snapshot']}")
        print(f"[INFO] version={manifest.get('version')} "
              f"kind={manifest.get('source', {}).get('kind')} "
              f"mode={manifest.get('source', {}).get('mode')} "
              f"created_at={manifest.get('created_at')}")
        for check in report["checks"]:
            print(f"[ OK ] {check}")
        for warning in report["warnings"]:
            print(f"[WARN] {warning}")
        for error in report["errors"]:
            print(f"[FAIL] {error}")
        print("[ OK ] 校验通过" if report["ok"] else "[FAIL] 校验未通过")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
