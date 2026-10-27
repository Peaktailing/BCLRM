"""schema 闸门与迁移台账（执行版 D14/D15 的最小实现）。

职责只有三件事：

1. 每个库用 ``PRAGMA user_version`` 记录已完成的 schema 版本；
2. 每个库用 ``schema_migrations`` 台账记录一次迁移的开始与结束，留下
   ``status='running'`` 的行说明上一次迁移半途而废，下次启动必须拒绝；
3. 提供**只读校验**入口，让 prod/beta 在启动时只比对、不迁移。

约定：
- 应用启动时，prod/beta 只校验；dev 允许自动迁移（保持本地开发手感）。
- 迁移由部署器在停服、冷备之后用 ``scripts/runtime_cli.py migrate`` 显式执行。
- 版本只能加不能减。新增迁移必须同时提升 ``MAIN_SCHEMA_VERSION`` 并在
  ``release.json`` 的 ``schema_versions`` 里同步，否则旧库不会重跑迁移。
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

#: 主业务库 schema 版本（四库分别记录，不共用一个号）
#: v2：person.must_change_password（beta 首登强改密）
MAIN_SCHEMA_VERSION = 2
#: 三个辅助库的 schema 版本
AUX_SCHEMA_VERSION = 1

MAIN_MIGRATION_ID = "main-schema-v2"
AUX_MIGRATION_ID = "aux-baseline-v1"

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    db_name TEXT NOT NULL,
    status TEXT NOT NULL,
    target_version INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    detail TEXT
)
"""


class SchemaError(RuntimeError):
    """schema 不满足启动条件：版本不符或存在未完成的迁移。"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def prepare(conn: sqlite3.Connection) -> None:
    """建立台账表（幂等）。"""
    conn.execute(LEDGER_DDL)
    conn.commit()


def version_of(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def assert_no_running(conn: sqlite3.Connection, db_name: str) -> None:
    """存在 running 记录说明上次迁移中断，必须人工/部署器恢复快照。"""
    prepare(conn)
    row = conn.execute(
        "SELECT id, started_at FROM schema_migrations "
        "WHERE db_name = ? AND status = 'running' ORDER BY started_at LIMIT 1",
        (db_name,),
    ).fetchone()
    if row:
        raise SchemaError(
            f"{db_name} 存在未完成的迁移 {row[0]}（开始于 {row[1]}）："
            "拒绝启动，请先用部署器恢复到快照或确认现场后人工收口"
        )


def begin_migration(conn: sqlite3.Connection, migration_id: str, db_name: str,
                    target_version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO schema_migrations"
        "(id, db_name, status, target_version, started_at, finished_at, detail)"
        " VALUES (?, ?, 'running', ?, ?, NULL, NULL)",
        (migration_id, db_name, target_version, _now()),
    )
    conn.commit()


def finish_migration(conn: sqlite3.Connection, migration_id: str,
                     target_version: int) -> None:
    """标记完成并推进 user_version（只在迁移主体成功之后调用）。"""
    conn.execute(
        "UPDATE schema_migrations SET status = 'ok', finished_at = ? "
        "WHERE id = ?",
        (_now(), migration_id),
    )
    # PRAGMA 不支持参数绑定；target_version 是模块内整数常量
    conn.execute(f"PRAGMA user_version = {int(target_version)}")
    conn.commit()


def stamp_if_blank(conn: sqlite3.Connection, db_name: str,
                   target_version: int) -> None:
    """给建表即最新的库盖章；已有 running 记录时不动。"""
    prepare(conn)
    if version_of(conn) >= target_version:
        return
    assert_no_running(conn, db_name)
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE db_name = ? AND status = 'ok' LIMIT 1",
        (db_name,),
    ).fetchone()
    if row:
        # 已有成功记录但 user_version 偏低：说明被手工改过，交给校验报错
        return
    begin_migration(conn, AUX_MIGRATION_ID, db_name, target_version)
    finish_migration(conn, AUX_MIGRATION_ID, target_version)


def open_readonly(db_path: str) -> sqlite3.Connection:
    """只读打开（不建库、不写 WAL）。文件不存在时抛 FileNotFoundError。"""
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"数据库不存在：{db_path}")
    uri = f"file:{path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def validate_readonly(db_path: str, db_name: str,
                      expected_version: Optional[int]) -> Dict[str, object]:
    """只读校验一个库：存在、可打开、无 running、版本等于预期。"""
    conn = open_readonly(db_path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        actual = version_of(conn)
        if expected_version is not None and actual != int(expected_version):
            raise SchemaError(
                f"{db_name} schema 版本不符：库为 {actual}，release 要求 "
                f"{expected_version}；请先用部署器显式迁移，不要直接启动应用"
            )
        if "schema_migrations" in tables:
            assert_no_running(conn, db_name)
        return {"db": db_name, "path": db_path, "user_version": actual}
    finally:
        conn.close()


def validate_map(schema_map: Dict[str, int],
                 paths: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    """校验四库。``schema_map`` 缺失某个库时跳过该库（仅 dev 允许）。"""
    from config.settings import (
        DB_ARCHIVE_PATH, DB_ATTACH_PATH, DB_LOG_PATH, DB_MAIN_PATH,
    )

    path_map = paths or {
        "main.db": DB_MAIN_PATH,
        "archive_cold.db": DB_ARCHIVE_PATH,
        "attach_cold.db": DB_ATTACH_PATH,
        "operation_log.db": DB_LOG_PATH,
    }
    results = {}
    for name, path in path_map.items():
        if name not in schema_map:
            continue
        results[name] = validate_readonly(path, name, schema_map[name])
    return results


def assert_complete(schema_map: Dict[str, int], require_all: bool = True) -> None:
    """prod/beta 的 schema map 必须覆盖四库。"""
    required: Iterable[str] = ("main.db", "archive_cold.db",
                               "attach_cold.db", "operation_log.db")
    missing = [name for name in required if name not in schema_map]
    if require_all and missing:
        raise SchemaError(
            "release.json 的 schema_versions 缺少：" + ", ".join(missing)
        )
