#!/usr/bin/env python3
"""异地归档备份 CLI（第二副本）。

把 ``<root>/backups/<env>/<kind>/<snapshot>`` 打成 tar.gz 上传到远端，
远端只保留一个 ``SHA256SUMS.txt``；本地已按保留策略清理的快照，其远端
归档与清单行会同步删除。

用法::

    python3 scripts/offsite_sync.py --root /home/biochm/BCLRM --env prod
    python3 scripts/offsite_sync.py --root /home/biochm/BCLRM --env beta --dry-run

远端默认 ``ph@210.45.37.13:/mnt/external_hdd/ph/DatabaseBackup``。
本机根分区不落备份数据：暂存归档默认写到 ``/data/bclrm/tmp/offsite``。

退出码：0 成功；2 参数/预检失败；3 执行失败（含 ssh、校验、清单回读）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
# 仓库内运行（scripts/）与部署副本（/home/biochm/BCLRM/ops/）都能找到 deploy 包
for _path in (HERE, PROJECT_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from deploy import offsite  # noqa: E402

DEFAULT_REMOTE = "ph@210.45.37.13:/mnt/external_hdd/ph/DatabaseBackup"
DEFAULT_TEMP = "/data/bclrm/tmp/offsite"


def _build_remote(spec: str, local_base: Optional[str],
                  ssh_key: Optional[str]):
    if local_base:
        return offsite.LocalRemote(Path(local_base))
    if ":" not in spec:
        raise offsite.OffsiteError("--remote 必须是 user@host:/absolute/path")
    host, _, base = spec.partition(":")
    if not base.startswith("/"):
        raise offsite.OffsiteError("远端路径必须是绝对路径")
    return offsite.SshRemote(host, base,
                             identity_file=Path(ssh_key) if ssh_key else None)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BCLRM 异地归档备份")
    parser.add_argument("--root", default="/home/biochm/BCLRM")
    parser.add_argument("--env", action="append", choices=("prod", "beta", "dev"),
                        help="可重复；默认 prod")
    parser.add_argument("--remote", default=DEFAULT_REMOTE,
                        help=f"远端 user@host:/path（默认 {DEFAULT_REMOTE}）")
    parser.add_argument("--local-base", default=None,
                        help="测试/离线：用本地目录充当远端")
    parser.add_argument("--ssh-key", default=None,
                        help="ssh 身份文件（默认 ~/.ssh/id_ed25519_13）")
    parser.add_argument("--temp-dir", default=DEFAULT_TEMP)
    parser.add_argument("--no-prune", action="store_true",
                        help="只上传不清理远端过期归档")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    envs = args.env or ["prod"]
    root = Path(args.root)
    if not (root / "backups").exists():
        print(f"[FAIL] 备份根不存在：{root / 'backups'}")
        return 2
    try:
        remote = _build_remote(args.remote, args.local_base, args.ssh_key)
    except offsite.OffsiteError as exc:
        print(f"[FAIL] 参数错误：{exc}")
        return 2

    try:
        result = offsite.sync(
            root, envs, remote, Path(args.temp_dir),
            prune=not args.no_prune, dry_run=args.dry_run,
        )
    except offsite.OffsiteError as exc:
        offsite.write_status(root, {
            "ok": False, "envs": envs, "error": str(exc)[:500],
        })
        print(f"[FAIL] 异地备份失败：{exc}")
        return 3

    offsite.write_status(root, dict(result, envs=envs))
    if args.json:
        print(json.dumps(dict(result, envs=envs), ensure_ascii=False, indent=2))
    else:
        if result.get("dry_run"):
            print(f"[DRY-RUN] 待上传 {len(result['planned_uploads'])} 份：")
            for rel in result["planned_uploads"]:
                print(f"  - {rel}")
        else:
            print(f"[ OK ] 上传 {len(result['uploaded'])} 份，"
                  f"清理 {len(result['pruned'])} 份，"
                  f"清单 {result['manifest_entries']} 条")
            for rel in result["uploaded"]:
                print(f"  + {rel}")
            for rel in result["pruned"]:
                print(f"  - {rel}")
            for warning in result["warnings"]:
                print(f"  ! {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
