#!/usr/bin/env python3
"""备份保留策略（执行版 4.5）。

规则：每日 7 天；每月 1/15 日保留过去 3 个自然月；升级前冷备最近 2 份且
不删当前回滚点；beta 最近 2 份；年度档在合规年限确认前永不自动删除；
release 只保留最近 3 个 + 所有仍被指针/部署记录/回滚点引用者。

默认 dry-run。``--releases`` 同时清理 release 目录；版本台账
（releases-index.json）保留历史，因此被删目录的版本号仍然禁止复用。

用法：
    python scripts/prune_backups.py --env prod
    python scripts/prune_backups.py --env prod --releases --execute

退出码：0 成功；2 参数/预检失败；3 执行失败。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deploy import release_layout as layout  # noqa: E402
from utils import backup as backup_mod  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BCLRM 备份与 release 保留策略")
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT))
    parser.add_argument("--env", choices=("prod", "beta"),
                        help="清理该环境的快照；不清理 release 时必填")
    parser.add_argument("--releases", action="store_true",
                        help="同时按“最近 3 个 + 被引用者”清理 release 目录")
    parser.add_argument("--now", help="ISO 时间（测试跨年/跨月用）")
    parser.add_argument("--execute", action="store_true",
                        help="真正删除；缺省只打印计划")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.env and not args.releases:
        parser.error("至少指定 --env 或 --releases")
    try:
        now = layout.parse_iso(args.now) if args.now else None
    except layout.LayoutError as exc:
        print(f"[FAIL] --now 非法：{exc}")
        return 2

    root = Path(args.root)
    snapshot_decisions: List[Dict[str, Any]] = []
    release_decisions: List[Dict[str, Any]] = []
    try:
        if args.env:
            snapshot_decisions = backup_mod.plan_prune(root, args.env, now=now)
        if args.releases:
            if not layout.releases_dir(root).is_dir():
                raise layout.LayoutError(f"release 目录不存在：{layout.releases_dir(root)}")
            release_decisions = backup_mod.plan_release_prune(root)
    except (layout.LayoutError, OSError) as exc:
        print(f"[FAIL] 预检失败：{exc}")
        return 2

    executed_snapshots: List[Dict[str, Any]] = []
    executed_releases: List[Dict[str, Any]] = []
    if args.execute:
        try:
            executed_snapshots = backup_mod.execute_prune(snapshot_decisions)
            executed_releases = backup_mod.execute_release_prune(release_decisions)
        except OSError as exc:
            print(f"[FAIL] 删除失败：{exc}")
            return 3

    payload = {
        "ok": True,
        "dry_run": not args.execute,
        "snapshots": snapshot_decisions,
        "releases": release_decisions,
        "deleted_snapshots": [item["snapshot"] for item in executed_snapshots],
        "deleted_releases": [item["release"] for item in executed_releases],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    prefix = "[EXECUTE]" if args.execute else "[DRY-RUN]"
    for decision in snapshot_decisions:
        marker = "DELETE" if decision["action"] == "delete" else "KEEP  "
        print(f"{prefix} {marker} {decision['kind']}/{decision['name']} "
              f"— {decision['reason']}")
    for decision in release_decisions:
        marker = "DELETE" if decision["action"] == "delete" else "KEEP  "
        print(f"{prefix} {marker} release {decision['version']} — {decision['reason']}")
    if not snapshot_decisions and not release_decisions:
        print(f"{prefix} 没有可处理的快照或 release")
    if not args.execute:
        print("[INFO] 以上仅为计划；加 --execute 才会删除")
    else:
        print(f"[ OK ] 已删除 {len(executed_snapshots)} 份快照、"
              f"{len(executed_releases)} 个 release")
    return 0


if __name__ == "__main__":
    sys.exit(main())
