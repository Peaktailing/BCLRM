#!/usr/bin/env python3
"""运行时 CLI：给部署器/发布工具调用的稳定入口（执行版 Stage 0A 交付项）。

三个子命令，语义固定，发布脚本只依赖它们：

    python scripts/runtime_cli.py check     # 只读：配置、schema map、库完整性
    python scripts/runtime_cli.py migrate   # 显式迁移（停服、冷备之后）
    python scripts/runtime_cli.py smoke     # 只读冒烟：不写任何业务数据

退出码：0 通过；2 配置或 schema 不满足；3 执行失败。
"""
import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (  # noqa: E402
    DB_ARCHIVE_PATH,
    DB_ATTACH_PATH,
    DB_LOG_PATH,
    DB_MAIN_PATH,
    ENV,
    IS_DEV,
    RELEASE_FILE,
    SCHEMA_VERSIONS,
    VERSION_NUMBER,
    ConfigError,
    describe_runtime,
    ensure_data_dirs,
)

_DBS = {
    "main.db": DB_MAIN_PATH,
    "archive_cold.db": DB_ARCHIVE_PATH,
    "attach_cold.db": DB_ATTACH_PATH,
    "operation_log.db": DB_LOG_PATH,
}


def _fail(message: str, code: int = 3) -> int:
    print(f"[FAIL] {message}")
    return code


def cmd_check() -> int:
    """只读检查：不建目录、不建表、不迁移。"""
    from db import schema_guard
    from db.database import validate_schemas

    print(f"[INFO] {describe_runtime()}")
    print(f"[INFO] release_file={RELEASE_FILE or '-'}")

    try:
        if SCHEMA_VERSIONS:
            results = validate_schemas(require_all=not IS_DEV)
        else:
            results = {}
            for name, path in _DBS.items():
                try:
                    results[name] = schema_guard.validate_readonly(path, name, None)
                except FileNotFoundError:
                    print(f"[WARN] {name} 不存在：{path}")
    except (ConfigError, schema_guard.SchemaError, FileNotFoundError) as exc:
        return _fail(str(exc), 2)

    for name, info in results.items():
        # 完整性检查放在只读连接上，不触碰 WAL
        conn = schema_guard.open_readonly(info["path"])
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            ok = bool(row) and row[0] == "ok"
        finally:
            conn.close()
        if not ok:
            return _fail(f"{name} integrity_check 未通过", 2)
        print(f"[ OK ] {name} user_version={info['user_version']} integrity=ok")

    missing = [n for n in _DBS if n not in results]
    if missing and not IS_DEV:
        return _fail("schema map 未覆盖：" + ", ".join(missing), 2)
    print(f"[ OK ] check 完成（env={ENV} version={VERSION_NUMBER}）")
    return 0


def cmd_migrate() -> int:
    """显式迁移：只在预期位置创建/升级 schema，成功后打印四库版本。"""
    from db import schema_guard
    from db.database import init_all_schemas, validate_schemas

    ensure_data_dirs()
    try:
        init_all_schemas()
        from services.base.system_config_service import ensure_defaults
        ensure_defaults()
        results = validate_schemas(require_all=not IS_DEV) if SCHEMA_VERSIONS else {}
    except Exception as exc:  # noqa: BLE001 - CLI 边界统一转退出码
        return _fail(f"迁移失败：{exc}")

    print(f"[INFO] {describe_runtime({k: v['user_version'] for k, v in results.items()} or None)}")
    for name, path in _DBS.items():
        conn = schema_guard.open_readonly(path)
        try:
            version = schema_guard.version_of(conn)
        finally:
            conn.close()
        expected = SCHEMA_VERSIONS.get(name)
        mark = "OK" if expected is None or version == expected else "MISMATCH"
        print(f"[{mark:^8}] {name} user_version={version} expected={expected}")
        if mark != "OK":
            return _fail(f"{name} 版本未达到 release 要求", 2)
    print("[ OK ] migrate 完成")
    return 0


def cmd_smoke() -> int:
    """只读冒烟：开只读连接做真实查询，禁止任何写路径。"""
    from db import schema_guard

    checks = []
    for name, path in _DBS.items():
        if not Path(path).is_file():
            return _fail(f"{name} 不存在：{path}", 2)
        conn = schema_guard.open_readonly(path)
        try:
            if name == "main.db":
                stats = {}
                for table in ("person", "reagent_bottle", "chemical_info", "borrow_order"):
                    try:
                        stats[table] = conn.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                    except sqlite3.DatabaseError:
                        stats[table] = -1
                checks.append(f"main {stats}")
            elif name == "attach_cold.db":
                count = conn.execute(
                    "SELECT COUNT(*) FROM attachment_index"
                ).fetchone()[0]
                checks.append(f"attach index={count}")
            elif name == "operation_log.db":
                count = conn.execute(
                    "SELECT COUNT(*) FROM operation_log"
                ).fetchone()[0]
                checks.append(f"log rows={count}")
            else:
                checks.append("archive ok")
        except sqlite3.DatabaseError as exc:
            return _fail(f"{name} 只读查询失败：{exc}", 2)
        finally:
            conn.close()

    from config.settings import ATTACHMENTS_DIR
    if not Path(ATTACHMENTS_DIR).is_dir():
        return _fail(f"附件目录不存在：{ATTACHMENTS_DIR}", 2)

    for line in checks:
        print(f"[ OK ] {line}")
    print("[ OK ] smoke 完成（只读）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="BCLRM 运行时 CLI")
    parser.add_argument("command", choices=("check", "migrate", "smoke"))
    args = parser.parse_args()

    try:
        if args.command == "check":
            return cmd_check()
        if args.command == "migrate":
            return cmd_migrate()
        return cmd_smoke()
    except ConfigError as exc:
        return _fail(str(exc), 2)


if __name__ == "__main__":
    sys.exit(main())
