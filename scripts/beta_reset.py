#!/usr/bin/env python3
"""beta 重建/修复（执行版 5.1、D12/D13）。

两种模式：

- ``release``：停 beta → 生产短停并冷备（由调用方完成，本工具要求传入已有
  冷备 id 且 ``--prod-stopped``）→ 把 prod 快照恢复到 beta → 清生产手机地址
  → 重置独立凭据 → 版本化 fixture → 可选显式迁移 → 写 reset_manifest。
- ``repair``：只处理 beta，绝不要求、也绝不触碰 prod；默认取最近一份已验证
  beta 快照。

秘密处理（D13）：超管独立强随机密码、其他账号各自一次性密码，只在标准输出
打印一次；不写日志、不写 reset_manifest、不进入任何制品。

退出码：0 成功；2 预检失败；3 执行失败。
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deploy import release_layout as layout  # noqa: E402
from utils import backup as backup_mod  # noqa: E402
from utils.password_utils import hash_password  # noqa: E402

FIXTURE_TEMPLATE = '''#!/usr/bin/env python3
"""beta 边界场景 fixture（版本 {schema}）。

契约：只允许使用 BETA- 前缀的业务编号，必须幂等（重复执行不新增重复数据），
不得读取任何真实生产导出文件。当前为 Stage 0B 骨架，未灌入真实业务数据。
"""
import sys


def seed() -> int:
    # TODO(Stage 1): 过期、零余量、部分归还、待审批、附件、多单位、归档场景
    print("[FIXTURE] beta_edge/{schema} 骨架：暂未灌入业务数据")
    return 0


if __name__ == "__main__":
    sys.exit(seed())
'''

FIXTURE_README = """# beta_edge fixture（schema {schema}）

- 用途：beta 每次重建后灌入可丢弃的边界场景数据。
- 约束：业务编号统一 `BETA-` 前缀；脚本必须幂等；禁止引用真实人员/台账。
- 当前状态：Stage 0B 只提供骨架，Stage 1 再补完整场景。
"""


class ResetError(RuntimeError):
    """执行失败。"""


def resolve_snapshot(args: argparse.Namespace) -> Path:
    if args.snapshot:
        return Path(args.snapshot)
    if args.cold_backup:
        value = Path(args.cold_backup)
        if value.is_dir():
            return value
        for kind in backup_mod.BACKUP_KINDS:
            candidate = layout.backups_dir(Path(args.root), "prod") / kind / str(args.cold_backup)
            if candidate.is_dir():
                return candidate
        raise layout.LayoutError(f"找不到冷备快照：{args.cold_backup}")
    if args.mode == "release":
        raise layout.LayoutError("release 模式必须传入 --cold-backup（prod 冷备 id）")
    latest = backup_mod.latest_snapshot(
        Path(args.root), "beta", require_verified=True
    )
    if latest is None:
        raise layout.LayoutError("beta 没有可用已验证快照，repair 无法继续")
    return latest


def resolve_release(root: Path, version: Optional[str]) -> Optional[Path]:
    if version:
        candidate = layout.release_dir(root, version)
        if not candidate.is_dir():
            raise layout.LayoutError(f"release 不存在：{candidate}")
        return candidate
    return layout.read_pointer(root, "beta")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def clear_mobile_base_url(main_db: Path) -> int:
    conn = _connect(main_db)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'"
        ).fetchone()
        if not row:
            raise ResetError("main.db 缺少 system_config，无法清理手机地址")
        cursor = conn.execute(
            "DELETE FROM system_config WHERE config_key = 'mobile.base_url'"
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def _person_columns(conn: sqlite3.Connection) -> List[str]:
    return [row[1] for row in conn.execute('PRAGMA table_info("person")')]


def reset_credentials(main_db: Path) -> List[Dict[str, Any]]:
    """为每个账号生成独立密码并立即写哈希；返回待一次性打印的账号清单。"""
    conn = _connect(main_db)
    try:
        if "person" not in {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }:
            raise ResetError("main.db 缺少 person 表")
        columns = _person_columns(conn)
        has_flag = "must_change_password" in columns
        rows = list(conn.execute(
            "SELECT id, name, role FROM person ORDER BY role = 'super_admin' DESC, id"
        ))
        accounts = []
        for row in rows:
            name = str(row["name"])
            role = str(row["role"] or "user")
            # 超管给更长随机串；普通账号一次性密码仍带 BETA- 前缀便于识别
            password = (
                secrets.token_urlsafe(24) if role == "super_admin"
                else "BETA-" + secrets.token_urlsafe(15)
            )
            fields = ["password_hash = ?"]
            params: List[Any] = [hash_password(password)]
            if has_flag:
                fields.append("must_change_password = 1")
            conn.execute(
                f"UPDATE person SET {', '.join(fields)} WHERE id = ?",
                (*params, row["id"]),
            )
            accounts.append({
                "name": name,
                "role": role,
                "password": password,
                "must_change_password": True,
                "flag_persisted": has_flag,
            })
        conn.commit()
    finally:
        conn.close()
    if not accounts:
        raise ResetError("person 表为空：beta 至少需要一个超管账号")
    return accounts


def ensure_fixture(fixture_root: Path, schema_version: int) -> Dict[str, Any]:
    """版本化 fixture 占位：缺失时建骨架，绝不生成真实业务数据。"""
    fixture_dir = Path(fixture_root) / str(schema_version)
    created = False
    if not fixture_dir.is_dir():
        fixture_dir.mkdir(parents=True)
        created = True
    seed = fixture_dir / "seed.py"
    readme = fixture_dir / "README.md"
    if not seed.is_file():
        seed.write_text(FIXTURE_TEMPLATE.format(schema=schema_version), encoding="utf-8")
        created = True
    if not readme.is_file():
        readme.write_text(FIXTURE_README.format(schema=schema_version), encoding="utf-8")
        created = True
    return {"dir": str(fixture_dir), "seed": str(seed), "created": created,
            "schema_version": schema_version}


def run_fixture(seed_path: Path, data_root: Path, release: Optional[Path]) -> Dict[str, Any]:
    environment = dict(os.environ)
    environment.update({
        "BCLRM_ENV": "beta",
        "BCLRM_DATA_DIR": str(data_root),
        "BCLRM_MOBILE_UI": "0",
    })
    python = sys.executable
    if release:
        environment["BCLRM_RELEASE_FILE"] = str(layout.release_json_path(release))
        python = layout.interpreter_for(release)
        payload = layout.payload_dir(release)
        environment["PYTHONPATH"] = (
            str(payload) + os.pathsep + environment.get("PYTHONPATH", "")
        )
    result = subprocess.run(
        [python, str(seed_path)], cwd=str(seed_path.parent),
        env=environment, capture_output=True, text=True, timeout=300,
    )
    return {"returncode": result.returncode,
            "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}


def reset(
    *, root: Path, mode: str, snapshot: Path, release: Optional[Path],
    prod_stopped: bool, migrate: bool, fixture_root: Path,
) -> Dict[str, Any]:
    target = layout.data_dir(root, "beta")
    report = backup_mod.verify_snapshot(snapshot)
    if not report["ok"]:
        raise ResetError("快照校验失败：" + "; ".join(report["errors"][:5]))
    manifest = report["manifest"]
    source_env = manifest["source"]["env"]
    if mode == "release" and source_env != "prod":
        raise ResetError(f"release 模式必须使用 prod 冷备，实际来源 {source_env}")
    if mode == "repair" and source_env != "beta":
        raise ResetError(f"repair 只能使用 beta 快照，实际来源 {source_env}")

    restored = backup_mod.restore_snapshot(snapshot, target, replace=True)
    main_db = target / "db" / "main.db"
    result: Dict[str, Any] = {
        "mode": mode,
        "snapshot": str(snapshot),
        "target": str(target),
        "restored": restored,
        "prod_stopped_declared": prod_stopped,
        "prod_touched": mode == "release",
        "migrate": None,
        "cleared_mobile_base_url": 0,
        "fixture": None,
        "accounts": [],
    }

    if migrate:
        if release is None:
            result["migrate"] = {"skipped": "无 beta 指针/release，未执行显式迁移"}
        else:
            migrated = layout.run_runtime_cli(release, "migrate", "beta", target)
            result["migrate"] = {
                "release": str(release), "returncode": migrated.returncode,
                "stdout": migrated.stdout[-2000:], "stderr": migrated.stderr[-2000:],
            }
            if migrated.returncode != 0:
                raise ResetError("显式迁移失败；beta 数据保持恢复现场，未启动")

    result["cleared_mobile_base_url"] = clear_mobile_base_url(main_db)

    conn = _connect(main_db)
    try:
        schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()

    fixture = ensure_fixture(fixture_root, schema_version)
    fixture["run"] = run_fixture(Path(fixture["seed"]), target, release)
    if fixture["run"]["returncode"] != 0:
        raise ResetError("fixture 执行失败：" + fixture["run"]["stderr"][:500])
    result["fixture"] = fixture

    accounts = reset_credentials(main_db)
    result["accounts"] = accounts
    manifest_path = target / "reset_manifest.json"
    layout.write_json_atomic(manifest_path, {
        "schema_version": schema_version,
        "mode": mode,
        "reset_at": layout.utc_now_iso(),
        "snapshot": {
            "path": str(snapshot),
            "created_at": manifest.get("created_at"),
            "manifest_sha256": layout.hash_file(Path(snapshot) / "manifest.json"),
            "source_env": source_env,
        },
        "release": str(release) if release else None,
        "version": manifest.get("version"),
        "git_sha": manifest.get("git_sha"),
        "schema": schema_version,
        "fixture": {"dir": fixture["dir"], "schema_version": schema_version,
                    "created": fixture["created"]},
        "accounts": [
            {"name": item["name"], "role": item["role"],
             "must_change_password": True,
             "flag_persisted": item["flag_persisted"]}
            for item in accounts
        ],
        "account_count": len(accounts),
        "passwords_recorded": False,
        "prod_stopped_declared": prod_stopped,
    })
    result["reset_manifest"] = str(manifest_path)
    result["flag_persisted"] = all(item["flag_persisted"] for item in accounts)
    return result


def _print_credentials(accounts: List[Dict[str, Any]]) -> None:
    print("=" * 66)
    print("以下密码只显示这一次，不写入日志/manifest；请当场交付并强制改密")
    print("=" * 66)
    for item in accounts:
        print(f"  {item['name']}  [{item['role']}]  {item['password']}")
    print("=" * 66)
    if not all(item["flag_persisted"] for item in accounts):
        print("[WARN] 当前 person 表没有 must_change_password 列，首登强改密需应用侧支持")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="重建/修复 beta 环境")
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT))
    parser.add_argument("--mode", required=True, choices=("release", "repair"))
    parser.add_argument("--cold-backup", help="prod 冷备目录或快照 id（release 必填）")
    parser.add_argument("--snapshot", help="显式快照目录")
    parser.add_argument("--release", help="用于显式迁移的 beta 版本（默认当前 beta 指针）")
    parser.add_argument("--prod-stopped", action="store_true",
                        help="release 模式：确认生产已停（短停窗口）")
    parser.add_argument("--migrate", dest="migrate", action="store_true", default=True,
                        help="恢复后执行显式迁移（默认开）")
    parser.add_argument("--no-migrate", dest="migrate", action="store_false")
    parser.add_argument("--fixture-root", type=Path,
                        help="fixture 根（默认 <root>/fixtures/beta_edge）")
    parser.add_argument("--execute", action="store_true", help="缺省 dry-run")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root)
    fixture_root = args.fixture_root or (root / "fixtures" / "beta_edge")
    try:
        if args.mode == "release" and not args.prod_stopped:
            raise layout.LayoutError(
                "release 模式必须先停生产并加 --prod-stopped（不接受“应该停了”的口头假设）"
            )
        snapshot = resolve_snapshot(args)
        if args.snapshot and args.cold_backup:
            raise layout.LayoutError("--snapshot 与 --cold-backup 只能给一个")
        verify = backup_mod.verify_snapshot(snapshot)
        if not verify["ok"]:
            raise backup_mod.BackupVerificationError(
                "快照校验失败：" + "; ".join(verify["errors"][:5])
            )
        source_env = verify["manifest"]["source"]["env"]
        if args.mode == "release" and source_env != "prod":
            raise layout.LayoutError(f"release 模式要求 prod 快照，实际 {source_env}")
        if args.mode == "repair" and source_env != "beta":
            raise layout.LayoutError(f"repair 只能使用 beta 快照，实际 {source_env}")
        release = resolve_release(root, args.release) if args.migrate else None
    except layout.LayoutError as exc:
        print(f"[FAIL] 预检失败：{exc}")
        return 2
    except backup_mod.BackupVerificationError as exc:
        print(f"[FAIL] 校验失败：{exc}")
        return 2

    if not args.execute:
        plan = {
            "mode": args.mode,
            "snapshot": str(snapshot),
            "target": str(layout.data_dir(root, "beta")),
            "release": str(release) if release else None,
            "migrate": bool(args.migrate and release),
            "fixture_root": str(fixture_root),
            "prod_stopped_declared": args.prod_stopped,
            "prod_touched": args.mode == "release",
        }
        if args.json:
            print(json.dumps({"ok": True, "dry_run": True, "plan": plan},
                             ensure_ascii=False, indent=2))
        else:
            print("[DRY-RUN] " + json.dumps(plan, ensure_ascii=False))
            print("[INFO] 快照校验通过；加 --execute 才会恢复 beta 与重置凭据")
        return 0

    try:
        result = reset(
            root=root, mode=args.mode, snapshot=snapshot, release=release,
            prod_stopped=args.prod_stopped, migrate=args.migrate,
            fixture_root=fixture_root,
        )
    except (ResetError, backup_mod.BackupVerificationError,
            backup_mod.BackupError, layout.LayoutError, OSError) as exc:
        print(f"[FAIL] beta 重置失败：{exc}")
        return 3

    _print_credentials(result["accounts"])
    summary = {key: value for key, value in result.items() if key != "accounts"}
    summary["ok"] = True
    summary["account_count"] = len(result["accounts"])
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"[ OK ] beta 已重建/修复：{result['target']}")
        print(f"[INFO] mode={result['mode']} version={result['restored']['version']} "
              f"accounts={len(result['accounts'])} "
              f"cleared_mobile_base_url={result['cleared_mobile_base_url']}")
        print(f"[INFO] reset_manifest={result['reset_manifest']}（不含任何密码）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
