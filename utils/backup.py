"""备份/恢复引擎（执行版第 4 节，Stage 0B）。

设计要点与“为什么”：

- **在线库备份统一走 ``sqlite3.Connection.backup()``**（D18）。直接复制
  ``*.db`` 会漏掉 WAL 里已提交但未 checkpoint 的页，得到一个“看起来能开、
  实际缺数据”的库；backup API 在源连接上加读锁复制一致快照。
- **先库后附件**：先把四库复制到快照目录并校验完整性与 schema，再打包附件。
  这样附件索引引用校验使用的是快照里的 attach_cold.db，而不是随时变化的
  在线库；缺失文件立即失败，不降级为警告。
- **数据包与配置包分开**（4.3）。常规恢复/回滚只恢复数据包；配置包只在
  整机灾难重建时显式恢复，避免把 beta 部署状态、版本退役记录回写成历史值。
- **manifest 四段合一**：来源、时间、冷/热、版本/git sha/工具版本、逐文件
  哈希、每库 user_version/行数/关键聚合/schema 快照。校验器只读 manifest
  与快照文件即可判断“这份快照能不能用来恢复”，不需要现场数据库。
- 本模块不依赖 ``config.settings``：工具要能在任意 ``--root``（测试用临时
  目录）上运行，路径全部由调用方传入。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from deploy import release_layout as layout  # noqa: E402
from utils.error_handler import logger  # noqa: E402

DB_NAMES = layout.DB_NAMES
BACKUP_KINDS = layout.BACKUP_KINDS
#: 低于该可用空间拒绝新快照（第 4.4 节）
MIN_FREE_GIB = 5.0

#: 关键聚合只取“能一眼看出业务量级”的计数；失败（表不存在）时跳过，
#: 不因为某个历史库缺表就让整份备份失败。
_AGGREGATE_SQL: Dict[str, List[Tuple[str, str]]] = {
    "main.db": [
        ("person_total", "SELECT COUNT(*) FROM person"),
        ("person_by_role", "SELECT role, COUNT(*) FROM person GROUP BY role"),
        ("chemical_total", "SELECT COUNT(*) FROM chemical_info"),
        ("bottle_total", "SELECT COUNT(*) FROM reagent_bottle"),
        ("bottle_by_status", "SELECT status, COUNT(*) FROM reagent_bottle GROUP BY status"),
        ("borrow_total", "SELECT COUNT(*) FROM borrow_order"),
        ("borrow_by_status", "SELECT status, COUNT(*) FROM borrow_order GROUP BY status"),
        ("attachment_refs", "SELECT ref_type, COUNT(*) FROM attachment_index GROUP BY ref_type"),
    ],
    "attach_cold.db": [
        ("index_total", "SELECT COUNT(*) FROM attachment_index"),
        ("by_category", "SELECT category, COUNT(*) FROM attachment_index GROUP BY category"),
    ],
    "operation_log.db": [
        ("log_total", "SELECT COUNT(*) FROM operation_log"),
    ],
    "archive_cold.db": [],
}


class BackupError(RuntimeError):
    """备份/恢复流程失败：调用方返回退出码 3。"""


class BackupVerificationError(RuntimeError):
    """快照校验不通过：调用方返回退出码 2。"""


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_stream(fh) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _open_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _integrity_ok(conn: sqlite3.Connection) -> bool:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    return bool(row) and row[0] == "ok"


def _user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def _table_names(conn: sqlite3.Connection) -> List[str]:
    return sorted(
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    )


def schema_snapshot(conn: sqlite3.Connection) -> Dict[str, Any]:
    """表/列/索引/视图快照：用于恢复后比对“结构是否真的回来了”。"""
    tables = _table_names(conn)
    columns = {}
    indexes = {}
    for table in tables:
        columns[table] = [
            {
                "name": row[1],
                "type": row[2],
                "notnull": int(row[3]),
                "pk": int(row[5]),
            }
            for row in conn.execute(f'PRAGMA table_info("{table}")')
        ]
        indexes[table] = sorted(
            row[1] for row in conn.execute(f'PRAGMA index_list("{table}")')
        )
    views = sorted(
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")
    )
    return {
        "tables": tables,
        "columns": columns,
        "indexes": indexes,
        "views": views,
        "user_version": _user_version(conn),
    }


def _row_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    counts = {}
    for table in _table_names(conn):
        try:
            counts[table] = int(
                conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
        except sqlite3.DatabaseError:
            counts[table] = -1
    return counts


def _key_aggregates(conn: sqlite3.Connection, db_name: str) -> Dict[str, Any]:
    aggregates: Dict[str, Any] = {}
    for name, sql in _AGGREGATE_SQL.get(db_name, []):
        try:
            rows = conn.execute(sql).fetchall()
        except sqlite3.DatabaseError:
            continue
        if len(rows) == 1 and len(rows[0]) == 1:
            aggregates[name] = int(rows[0][0])
        else:
            aggregates[name] = {str(row[0]): int(row[1]) for row in rows}
    return aggregates


def _running_migrations(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE status = 'running'"
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.DatabaseError:
        return 0


def _sha_file_list(root: Path) -> List[Dict[str, Any]]:
    root = Path(root)
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        entries.append({
            "name": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": hash_file(path),
        })
    return entries


# ---------------------------------------------------------------------------
# 在线库备份
# ---------------------------------------------------------------------------
def _backup_database(source: Path, target: Path) -> None:
    """单库在线备份。源只读打开，避免误改生产库或生成新 WAL。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{Path(source).resolve()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
            # 快照库统一回到 DELETE 日志模式：恢复/校验时不需要 -wal/-shm，
            # 也不会因为只读打开缺 shm 而失败。
            dst.execute("PRAGMA journal_mode=DELETE")
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()


# ---------------------------------------------------------------------------
# 附件
# ---------------------------------------------------------------------------
def _index_references(attach_db: Path) -> List[str]:
    conn = _open_readonly(attach_db)
    try:
        tables = set(_table_names(conn))
        if "attachment_index" not in tables:
            return []
        return [str(row[0]) for row in conn.execute(
            "SELECT stored_name FROM attachment_index WHERE stored_name IS NOT NULL"
        )]
    finally:
        conn.close()


def _build_attachments(attachments_dir: Path, archive: Path,
                       attach_db: Path) -> Dict[str, Any]:
    """附件 tar + 逐文件哈希 + 索引引用校验。

    索引里的文件必须存在；物理文件多余只记为 orphan（允许，说明索引被删过
    但文件没清），不能因为孤儿文件让整份备份失败。
    """
    attachments_dir = Path(attachments_dir)
    if not attachments_dir.is_dir():
        raise BackupError(f"附件目录不存在：{attachments_dir}")
    files = _sha_file_list(attachments_dir)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w") as tar:
        for entry in files:
            path = attachments_dir / entry["name"]
            info = tar.gettarinfo(str(path), arcname=entry["name"])
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(path, "rb") as fh:
                tar.addfile(info, fh)

    names = {entry["name"] for entry in files}
    basenames = {Path(name).name for name in names}
    references = _index_references(attach_db)
    missing = [name for name in references if Path(name).name not in basenames]
    referenced_basenames = {Path(name).name for name in references}
    orphans = sorted(
        entry["name"] for entry in files
        if Path(entry["name"]).name not in referenced_basenames
    )
    if missing:
        raise BackupError(
            "附件索引引用的文件缺失（拒绝生成不可恢复快照）："
            + ", ".join(missing[:10])
        )
    return {
        "archive": "data/attachments.tar",
        "sha256": hash_file(archive),
        "size": archive.stat().st_size,
        "file_count": len(files),
        "index_entries": len(references),
        "missing": missing,
        "orphans": orphans,
        "orphan_count": len(orphans),
        "files": files,
    }


# ---------------------------------------------------------------------------
# 配置包（含脱敏）
# ---------------------------------------------------------------------------
_SECRET_KEY_PATTERN = ("PASS", "SECRET", "TOKEN", "KEY", "CREDENTIAL")


def _redact_env_bytes(data: bytes) -> bytes:
    """env 文件允许存在，但不允许把明文密码带进配置包。"""
    lines = []
    for raw in data.decode("utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip().upper()
            if any(token in key for token in _SECRET_KEY_PATTERN):
                lines.append(f"{stripped.split('=', 1)[0]}=<redacted>")
                continue
        lines.append(raw)
    return ("\n".join(lines) + "\n").encode("utf-8")


def _config_candidates(root: Path) -> List[Path]:
    root = Path(root)
    files: List[Path] = []
    for pattern in (
        "env/*.env",
        "systemd/user/*",
        "releases-index.json",
        "release_train.json",
        "logs/cron_status.json",
        "deployments/*.json",
        "acceptance/*.json",
        "legacy/*/legacy_manifest.json",
    ):
        files.extend(sorted(root.glob(pattern)))
    for env in ("prod", "beta"):
        current = layout.read_pointer(root, env)
        if current:
            for name in ("release.json", "payload/requirements.lock"):
                candidate = current / name
                if candidate.is_file():
                    files.append(candidate)
    return [path for path in files if path.is_file()]


def _build_config_bundle(root: Path, archive: Path) -> Dict[str, Any]:
    """配置包：非秘密 env、units、锁、release/deploy 元数据、指针状态。"""
    entries = []
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w") as tar:
        for path in _config_candidates(root):
            if path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            data = path.read_bytes()
            if path.suffix == ".env":
                data = _redact_env_bytes(data)
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            info.mtime = int(path.stat().st_mtime)
            info.mode = 0o600 if path.suffix == ".env" else 0o644
            tar.addfile(info, BytesIO(data))
            entries.append({"name": rel, "size": len(data),
                            "sha256": hashlib.sha256(data).hexdigest()})
        pointers = {
            env: layout.pointer_target_name(root, env) for env in ("prod", "beta")
        }
        payload = json.dumps(pointers, ensure_ascii=False, indent=2).encode("utf-8")
        info = tarfile.TarInfo("pointers.json")
        info.size = len(payload)
        info.mode = 0o644
        tar.addfile(info, BytesIO(payload))
        entries.append({"name": "pointers.json", "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()})
    return {
        "archive": "config/config.tar",
        "sha256": hash_file(archive),
        "size": archive.stat().st_size,
        "files": entries,
    }


# ---------------------------------------------------------------------------
# 生成快照
# ---------------------------------------------------------------------------
def _snapshot_id(now: datetime, version: Optional[str]) -> str:
    base = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{version or 'noversion'}"
    return base


def _unique_snapshot_dir(kind_dir: Path, snapshot_id: str) -> Path:
    candidate = kind_dir / snapshot_id
    index = 2
    while candidate.exists():
        candidate = kind_dir / f"{snapshot_id}-{index}"
        index += 1
    return candidate


def _release_identity(root: Path, env: str) -> Dict[str, Any]:
    current = layout.read_pointer(root, env)
    if not current:
        return {"version": None, "git_sha": None, "artifact_sha256": None,
                "release_path": None}
    try:
        doc = layout.read_release(current)
    except layout.LayoutError as exc:
        logger.warning("读取当前 release 失败，快照将不记录版本信息", extra={"error": str(exc)})
        return {"version": None, "git_sha": None, "artifact_sha256": None,
                "release_path": str(current)}
    return {
        "version": doc["version"],
        "git_sha": doc["git_sha"],
        "artifact_sha256": doc["artifact_sha256"],
        "release_path": str(current),
    }


def create_backup(
    root: Path,
    env: str,
    kind: str,
    *,
    mode: str = "hot",
    source: str = "manual",
    label: str = "",
    service_stopped: bool = False,
    now: Optional[datetime] = None,
    min_free_gib: float = MIN_FREE_GIB,
) -> Dict[str, Any]:
    """生成一份四段一体快照，返回 snapshot 路径与 manifest。

    ``mode='cold'`` 要求调用方先用 ``service_stopped=True`` 证明服务已停；
    工具本身无法可靠探测进程，因此宁可由调用方显式承诺，也不偷偷热备。
    """
    root = Path(root)
    if env not in ("prod", "beta", "dev"):
        raise BackupError(f"未知环境：{env}")
    if kind not in BACKUP_KINDS:
        raise BackupError(f"未知备份类型：{kind}")
    if mode not in ("hot", "cold"):
        raise BackupError(f"未知备份模式：{mode}")
    if mode == "cold" and not service_stopped:
        raise BackupError("冷备要求调用方确认服务已停（--service-stopped）")
    layout.ensure_backup_volume(root)

    data_root = layout.data_dir(root, env)
    db_dir = data_root / "db"
    if not db_dir.is_dir():
        raise BackupError(f"数据根缺少 db 目录：{db_dir}（环境未初始化？）")
    missing_dbs = [name for name in DB_NAMES if not (db_dir / name).is_file()]
    if missing_dbs:
        raise BackupError("四库不齐，拒绝生成不可恢复快照：" + ", ".join(missing_dbs))

    free = shutil.disk_usage(str(root)).free / (1024 ** 3)
    if free < min_free_gib:
        raise BackupError(
            f"根分区可用空间 {free:.1f} GiB 低于 {min_free_gib} GiB，拒绝新备份"
        )

    stamp = _now(now)
    identity = _release_identity(root, env)
    kind_dir = layout.backups_dir(root, env) / kind
    kind_dir.mkdir(parents=True, exist_ok=True)
    final_dir = _unique_snapshot_dir(kind_dir, _snapshot_id(stamp, identity["version"]))
    staging = kind_dir / f".tmp-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True)

    try:
        db_target = staging / "data" / "db"
        db_target.mkdir(parents=True)
        databases: Dict[str, Any] = {}
        schema_versions: Dict[str, int] = {}
        for name in DB_NAMES:
            source_db = db_dir / name
            target_db = db_target / name
            _backup_database(source_db, target_db)
            conn = _open_readonly(target_db)
            try:
                if not _integrity_ok(conn):
                    raise BackupError(f"{name} 备份后 integrity_check 未通过")
                running = _running_migrations(conn)
                if running:
                    raise BackupError(
                        f"{name} 存在 {running} 条 running 迁移台账，"
                        "现场已半程中断，先处理再备份"
                    )
                version = _user_version(conn)
                schema = schema_snapshot(conn)
                databases[name] = {
                    "file": f"data/db/{name}",
                    "size": target_db.stat().st_size,
                    "sha256": hash_file(target_db),
                    "user_version": version,
                    "integrity": "ok",
                    "row_counts": _row_counts(conn),
                    "aggregates": _key_aggregates(conn, name),
                    "schema": schema,
                }
                schema_versions[name] = version
            finally:
                conn.close()

        attachments = _build_attachments(
            data_root / "attachments", staging / "data" / "attachments.tar",
            db_target / "attach_cold.db",
        )
        config = _build_config_bundle(root, staging / "config" / "config.tar")

        manifest = {
            "manifest_version": 1,
            "tool": {
                "name": layout.TOOL_NAME,
                "version": layout.TOOL_VERSION,
                "python_version": sys.version.split()[0],
                "hostname": socket.gethostname(),
            },
            "source": {
                "env": env,
                "kind": kind,
                "mode": mode,
                "data_root": str(data_root),
                "label": label,
                "origin": source,
                "service_stopped": bool(service_stopped),
            },
            "created_at": _iso(stamp),
            "version": identity["version"],
            "git_sha": identity["git_sha"],
            "release": {
                "artifact_sha256": identity["artifact_sha256"],
                "path": identity["release_path"],
            },
            "schema_versions": schema_versions,
            "databases": databases,
            "attachments": attachments,
            "config": config,
            "checks": {
                "databases_ok": True,
                "attachments_ok": True,
                "index_refs_ok": True,
                "self_consistent": True,
            },
        }
        layout.write_json_atomic(staging / "manifest.json", manifest)
        os.replace(staging, final_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    report = verify_snapshot(final_dir)
    if not report["ok"]:
        shutil.rmtree(final_dir, ignore_errors=True)
        raise BackupError("新快照自校验失败：" + "; ".join(report["errors"][:5]))
    logger.info(
        "备份完成",
        extra={"snapshot": str(final_dir), "env": env, "kind": kind, "mode": mode},
    )
    return {"snapshot": str(final_dir), "manifest": manifest, "verification": report}


# ---------------------------------------------------------------------------
# 校验（只读）
# ---------------------------------------------------------------------------
def load_manifest(snapshot: Path) -> Dict[str, Any]:
    path = Path(snapshot) / "manifest.json"
    if not path.is_file():
        raise BackupVerificationError(f"快照缺少 manifest.json：{snapshot}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupVerificationError(f"manifest 无法解析：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise BackupVerificationError("manifest 顶层必须是对象")
    return data


def _verify_db(snapshot: Path, name: str, manifest: Dict[str, Any],
               errors: List[str], checks: List[str]) -> None:
    entry = manifest.get("databases", {}).get(name)
    if not isinstance(entry, dict):
        errors.append(f"manifest 缺少数据库条目：{name}")
        return
    db_path = Path(snapshot) / str(entry.get("file", ""))
    if not db_path.is_file():
        errors.append(f"{name} 文件缺失：{entry.get('file')}")
        return
    if hash_file(db_path) != entry.get("sha256"):
        errors.append(f"{name} sha256 与 manifest 不一致")
        return
    if db_path.stat().st_size != entry.get("size"):
        errors.append(f"{name} 大小与 manifest 不一致")
    conn = _open_readonly(db_path)
    try:
        if not _integrity_ok(conn):
            errors.append(f"{name} integrity_check 未通过")
        actual = _user_version(conn)
        if actual != entry.get("user_version"):
            errors.append(
                f"{name} user_version={actual} 与 manifest={entry.get('user_version')} 不一致"
            )
        if manifest.get("schema_versions", {}).get(name) != actual:
            errors.append(f"{name} 不在 schema_versions 或版本不一致")
        running = _running_migrations(conn)
        if running:
            errors.append(f"{name} 存在 {running} 条 running 迁移（半程现场不可恢复）")
    finally:
        conn.close()
    checks.append(f"{name} hash/integrity/version ok")


def _verify_attachments(snapshot: Path, manifest: Dict[str, Any],
                        errors: List[str], checks: List[str]) -> None:
    entry = manifest.get("attachments")
    if not isinstance(entry, dict):
        errors.append("manifest 缺少 attachments 段")
        return
    archive = Path(snapshot) / str(entry.get("archive", ""))
    if not archive.is_file():
        errors.append(f"附件包缺失：{entry.get('archive')}")
        return
    if hash_file(archive) != entry.get("sha256"):
        errors.append("附件包 sha256 与 manifest 不一致")
        return
    if archive.stat().st_size != entry.get("size"):
        errors.append("附件包大小与 manifest 不一致")

    expected = {item["name"]: item for item in entry.get("files") or []}
    seen = set()
    count = 0
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            count += 1
            seen.add(member.name)
            item = expected.get(member.name)
            if item is None:
                errors.append(f"附件包出现 manifest 未登记文件：{member.name}")
                continue
            extracted = tar.extractfile(member)
            digest = _hash_stream(extracted) if extracted else ""
            if digest != item.get("sha256"):
                errors.append(f"附件哈希不一致：{member.name}")
            if member.size != item.get("size"):
                errors.append(f"附件大小不一致：{member.name}")
    if len(expected) != count:
        errors.append(f"附件文件数 {count} 与 manifest {len(expected)} 不一致")
    if entry.get("file_count") != count:
        errors.append(f"manifest file_count={entry.get('file_count')} 与实际 {count} 不一致")

    attach_entry = manifest.get("databases", {}).get("attach_cold.db") or {}
    attach_path = Path(snapshot) / str(attach_entry.get("file", ""))
    if attach_path.is_file():
        references = _index_references(attach_path)
        basenames = {Path(name).name for name in seen}
        missing = [name for name in references if Path(name).name not in basenames]
        if missing:
            errors.append("附件索引引用缺失：" + ", ".join(missing[:5]))
        elif entry.get("missing"):
            errors.append("manifest 记录了缺失附件却仍标为通过")
    checks.append(f"attachments {count} files hash ok")


def _verify_config(snapshot: Path, manifest: Dict[str, Any],
                   errors: List[str], checks: List[str]) -> None:
    entry = manifest.get("config")
    if not entry:
        return
    archive = Path(snapshot) / str(entry.get("archive", ""))
    if not archive.is_file():
        errors.append("配置包缺失")
        return
    if hash_file(archive) != entry.get("sha256"):
        errors.append("配置包 sha256 不一致")
        return
    expected = {item["name"]: item for item in entry.get("files") or []}
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            extracted = tar.extractfile(member)
            digest = _hash_stream(extracted) if extracted else ""
            item = expected.get(member.name)
            if item is None or item.get("sha256") != digest:
                errors.append(f"配置包文件哈希不一致：{member.name}")
    checks.append(f"config {len(expected)} files hash ok")


def verify_snapshot(snapshot: Path) -> Dict[str, Any]:
    """只读校验：哈希、完整性、manifest 自洽、索引引用。

    不写快照、不建临时库；失败返回 ``ok=False`` 与具体错误，由 CLI 转成
    退出码 2。调用方（restore/deploy/rehearse）必须先过这一步。
    """
    snapshot = Path(snapshot)
    report: Dict[str, Any] = {
        "snapshot": str(snapshot),
        "ok": False,
        "errors": [],
        "warnings": [],
        "checks": [],
        "manifest": None,
    }
    try:
        manifest = load_manifest(snapshot)
    except BackupVerificationError as exc:
        report["errors"].append(str(exc))
        return report
    report["manifest"] = manifest

    required = ("tool", "source", "created_at", "databases", "attachments",
                "schema_versions", "checks")
    lacking = [key for key in required if key not in manifest]
    if lacking:
        report["errors"].append("manifest 缺字段：" + ", ".join(lacking))
        return report
    try:
        layout.parse_iso(manifest["created_at"])
    except layout.LayoutError as exc:
        report["errors"].append(str(exc))
    source = manifest.get("source") or {}
    if source.get("mode") not in ("hot", "cold"):
        report["errors"].append("manifest source.mode 非法")
    if source.get("env") not in ("prod", "beta", "dev"):
        report["errors"].append("manifest source.env 非法")
    if manifest.get("version"):
        try:
            layout.normalize_version(manifest["version"])
        except layout.LayoutError as exc:
            report["errors"].append(str(exc))
    if manifest.get("git_sha") and len(str(manifest["git_sha"])) != 40:
        report["errors"].append("manifest git_sha 不是完整 sha")
    if not isinstance(manifest.get("schema_versions"), dict):
        report["errors"].append("manifest schema_versions 必须是对象")

    for name in DB_NAMES:
        _verify_db(snapshot, name, manifest, report["errors"], report["checks"])
    _verify_attachments(snapshot, manifest, report["errors"], report["checks"])
    _verify_config(snapshot, manifest, report["errors"], report["checks"])

    flags = manifest.get("checks") or {}
    if not all(flags.get(key) for key in (
        "databases_ok", "attachments_ok", "index_refs_ok", "self_consistent"
    )):
        report["errors"].append("manifest.checks 未全部为 true（生成时就不自洽）")
    if manifest.get("attachments", {}).get("missing"):
        report["errors"].append("manifest 记录了缺失附件")
    if report["errors"]:
        return report
    report["ok"] = True
    report["checks"].append("manifest 自洽")
    return report


# ---------------------------------------------------------------------------
# 恢复
# ---------------------------------------------------------------------------
def _check_db_file(path: Path, entry: Dict[str, Any]) -> None:
    """校验一个已落盘库文件的哈希、完整性与版本（不做复制）。"""
    if hash_file(path) != entry.get("sha256"):
        raise BackupVerificationError(f"恢复后哈希不一致：{path.name}")
    conn = _open_readonly(path)
    try:
        if not _integrity_ok(conn):
            raise BackupVerificationError(f"{path.name} 恢复后完整性失败")
        if _user_version(conn) != entry.get("user_version"):
            raise BackupVerificationError(f"{path.name} 恢复后 user_version 不符")
    finally:
        conn.close()


def _copy_verified_db(source: Path, target: Path, entry: Dict[str, Any]) -> None:
    if hash_file(source) != entry.get("sha256"):
        raise BackupVerificationError(f"恢复前哈希不一致：{source.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    _check_db_file(target, entry)


def _extract_attachments(archive: Path, target: Path, entry: Dict[str, Any]) -> int:
    target.mkdir(parents=True, exist_ok=True)
    expected = {item["name"] for item in entry.get("files") or []}
    layout.safe_extract_tar(archive, target)
    actual = {path.relative_to(target).as_posix()
              for path in target.rglob("*") if path.is_file()}
    if actual != expected:
        missing = sorted(expected - actual)[:5]
        extra = sorted(actual - expected)[:5]
        raise BackupVerificationError(
            f"附件恢复后文件集合不一致（缺 {missing}，多 {extra}）"
        )
    return len(actual)


def restore_snapshot(
    snapshot: Path,
    target: Path,
    *,
    replace: bool = False,
    merge: bool = False,
    include_config: bool = False,
    config_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """恢复数据包到显式目标；先校验、后恢复、再校验。

    目标目录已存在时必须显式 ``replace=True``，旧目录会被改名为
    ``.<name>.replaced-<时间>`` 保留现场，而不是直接删除。

    ``merge=True`` 只替换目标下的 ``db/`` 与 ``attachments/``，保留目录中的
    代码等其它内容；legacy 回滚用这种模式，避免把 legacy 应用代码删掉。
    """
    snapshot = Path(snapshot)
    target = Path(target)
    if not target.is_absolute():
        raise BackupVerificationError(f"恢复目标必须是绝对路径：{target}")
    report = verify_snapshot(snapshot)
    if not report["ok"]:
        raise BackupVerificationError("快照校验失败：" + "; ".join(report["errors"][:5]))
    manifest = report["manifest"]
    if include_config and config_root is None:
        raise BackupVerificationError("恢复配置包必须指定 root")
    if merge and not target.is_dir():
        raise BackupVerificationError(f"merge 恢复要求目标目录已存在：{target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.restore-{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    replaced_from = None
    try:
        db_target = staging / "db"
        db_target.mkdir()
        for name in DB_NAMES:
            entry = manifest["databases"][name]
            _copy_verified_db(snapshot / entry["file"], db_target / name, entry)
        attachments_entry = manifest["attachments"]
        count = _extract_attachments(
            snapshot / attachments_entry["archive"], staging / "attachments",
            attachments_entry,
        )

        if include_config:
            config_entry = manifest.get("config") or {}
            archive = snapshot / str(config_entry.get("archive", ""))
            if archive.is_file():
                layout.safe_extract_tar(archive, Path(config_root))

        if merge:
            replaced_parts = []
            stamp = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
            for sub in ("db", "attachments"):
                destination = target / sub
                if destination.exists():
                    old_part = target / f".{sub}.replaced-{stamp}"
                    os.replace(destination, old_part)
                    replaced_parts.append(str(old_part))
                os.replace(staging / sub, destination)
            shutil.rmtree(staging, ignore_errors=True)
            replaced_from = replaced_parts or None
        else:
            if target.exists():
                if not replace:
                    raise BackupVerificationError(
                        f"目标已存在且未指定 --replace：{target}"
                    )
                replaced_from = target.parent / (
                    f".{target.name}.replaced-"
                    f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
                )
                os.replace(target, replaced_from)
            os.replace(staging, target)
            replaced_from = str(replaced_from) if replaced_from else None

        # 恢复后再校验一遍：以目标现场为准，而不是相信 staging
        for name in DB_NAMES:
            entry = manifest["databases"][name]
            _check_db_file(target / "db" / name, entry)
        restored_files = {
            path.relative_to(target / "attachments").as_posix()
            for path in (target / "attachments").rglob("*") if path.is_file()
        }
        expected_files = {item["name"] for item in attachments_entry.get("files") or []}
        if restored_files != expected_files:
            raise BackupVerificationError("恢复后附件文件集合与 manifest 不一致")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    logger.info("恢复完成", extra={"snapshot": str(snapshot), "target": str(target)})
    return {
        "target": str(target),
        "snapshot": str(snapshot),
        "replaced_from": str(replaced_from) if replaced_from else None,
        "attachments_files": count,
        "version": manifest.get("version"),
        "git_sha": manifest.get("git_sha"),
        "schema_versions": manifest.get("schema_versions"),
    }


# ---------------------------------------------------------------------------
# 复制 / 第二副本
# ---------------------------------------------------------------------------
def clone_snapshot(
    source_snapshot: Path,
    root: Path,
    env: str,
    kind: str,
    *,
    origin: str = "copy",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """把已验证快照复制成新的保留类型（半月档从已验证备份复制，4.5）。"""
    root = Path(root)
    if kind not in BACKUP_KINDS:
        raise BackupError(f"未知备份类型：{kind}")
    layout.ensure_backup_volume(root)
    report = verify_snapshot(source_snapshot)
    if not report["ok"]:
        raise BackupVerificationError("源快照校验失败，拒绝复制")
    manifest = report["manifest"]
    stamp = _now(now)
    version = manifest.get("version")
    kind_dir = layout.backups_dir(root, env) / kind
    kind_dir.mkdir(parents=True, exist_ok=True)
    final_dir = _unique_snapshot_dir(kind_dir, _snapshot_id(stamp, version))
    staging = kind_dir / f".tmp-{uuid.uuid4().hex[:8]}"
    shutil.copytree(source_snapshot, staging)
    try:
        copied = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
        copied["created_at"] = _iso(stamp)
        copied["copy"] = {
            "source": str(source_snapshot),
            "source_created_at": manifest.get("created_at"),
            "kind": kind,
            "origin": origin,
        }
        copied["source"]["kind"] = kind
        layout.write_json_atomic(staging / "manifest.json", copied)
        os.replace(staging, final_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    result = verify_snapshot(final_dir)
    if not result["ok"]:
        shutil.rmtree(final_dir, ignore_errors=True)
        raise BackupError("复制后的快照校验失败")
    return {"snapshot": str(final_dir), "manifest": copied, "verification": result}


def copy_to_second_location(snapshot: Path, destination_root: Path,
                            env: str) -> Dict[str, Any]:
    """第二副本：跨盘只复制并重新校验，禁止硬链接（D20）。"""
    snapshot = Path(snapshot)
    destination_root = Path(destination_root)
    if not destination_root.is_dir():
        raise BackupError(f"第二副本根不存在（挂载丢失？）：{destination_root}")
    if not os.access(destination_root, os.W_OK):
        raise BackupError(f"第二副本根不可写：{destination_root}")
    kind = snapshot.parent.name
    target = destination_root / env / kind / snapshot.name
    if target.exists():
        raise BackupError(f"第二副本目标已存在：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot, target)
    report = verify_snapshot(target)
    if not report["ok"]:
        shutil.rmtree(target, ignore_errors=True)
        raise BackupError("第二副本重新校验失败：" + "; ".join(report["errors"][:3]))
    return {"target": str(target), "verification": report}


# ---------------------------------------------------------------------------
# 保留策略（4.5）
# ---------------------------------------------------------------------------
def _manifest_created_at(snapshot: Path) -> Optional[datetime]:
    try:
        manifest = load_manifest(snapshot)
        return layout.parse_iso(manifest["created_at"])
    except (BackupVerificationError, layout.LayoutError, KeyError):
        return None


def list_snapshots(root: Path, env: str,
                   kind: Optional[str] = None) -> List[Dict[str, Any]]:
    base = layout.backups_dir(root, env)
    kinds = [kind] if kind else list(BACKUP_KINDS)
    snapshots = []
    for kind_name in kinds:
        kind_dir = base / kind_name
        if not kind_dir.is_dir():
            continue
        for path in sorted(kind_dir.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            created = _manifest_created_at(path)
            snapshots.append({
                "path": path,
                "name": path.name,
                "kind": kind_name,
                "created_at": created,
            })
    return snapshots


def _protected_snapshot_names(root: Path, env: str) -> Dict[str, str]:
    """当前回滚点、部署记录引用、最近验证快照不得删除。"""
    protected: Dict[str, str] = {}
    for name in collect_deployment_snapshot_names(layout.deployment_file(root, env)):
        protected[name] = "部署/回滚记录引用"
    verified_file = layout.backups_dir(root, env) / "last_verified.json"
    if verified_file.is_file():
        try:
            data = json.loads(verified_file.read_text(encoding="utf-8"))
            value = data.get("snapshot")
            if value:
                protected[Path(str(value)).name] = "最近验证快照"
        except (OSError, ValueError):
            pass
    snapshots = [s for s in list_snapshots(root, env) if s["created_at"]]
    if snapshots:
        newest = max(snapshots, key=lambda s: s["created_at"])
        protected[newest["name"]] = "最后一份快照"
    return protected


def collect_deployment_snapshot_names(deployment_path: Path) -> List[str]:
    """从部署记录递归找快照目录名；兼容字符串与 {path/name} 两种写法。"""
    if not Path(deployment_path).is_file():
        return []
    try:
        data = json.loads(Path(deployment_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    names: List[str] = []

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, child_key)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str) and value:
            if "backups/" in value or key in (
                "snapshot", "backup", "rollback_snapshot", "cold_backup"
            ):
                names.append(Path(value).name)

    walk(data)
    return sorted(set(names))


def plan_prune(root: Path, env: str, *,
               now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """返回逐快照决策；默认只出计划，执行由 ``execute_prune`` 负责。"""
    root = Path(root)
    reference = _now(now)
    today = reference.date()
    protected = _protected_snapshot_names(root, env)
    snapshots = list_snapshots(root, env)
    decisions: List[Dict[str, Any]] = []

    def decide(snapshot: Dict[str, Any], action: str, reason: str) -> None:
        decisions.append({
            "snapshot": str(snapshot["path"]),
            "name": snapshot["name"],
            "kind": snapshot["kind"],
            "created_at": snapshot["created_at"].isoformat() if snapshot["created_at"] else None,
            "action": action,
            "reason": reason,
        })

    for snapshot in snapshots:
        created = snapshot["created_at"]
        kind = snapshot["kind"]
        if created is None:
            decide(snapshot, "keep", "manifest 不可读，保留待人工判断")
            continue
        if snapshot["name"] in protected:
            decide(snapshot, "keep", protected[snapshot["name"]])
            continue
        if kind == "annual":
            decide(snapshot, "keep", "年度冷存：合规期限确认前禁止自动删除（D22）")
            continue

        if env == "beta":
            ordered = sorted(
                [s for s in snapshots if s["created_at"]],
                key=lambda s: s["created_at"], reverse=True,
            )
            if snapshot in ordered[:2]:
                decide(snapshot, "keep", "beta 最近 2 份")
            else:
                decide(snapshot, "delete", "beta 只保留最近 2 份")
            continue

        if kind == "daily":
            if created.date() >= today - timedelta(days=6):
                decide(snapshot, "keep", "每日备份保留最近 7 天")
            else:
                decide(snapshot, "delete", "超出每日 7 天窗口")
        elif kind == "semimonthly":
            allowed = {(today.year, today.month)}
            year, month = today.year, today.month
            for _ in range(2):
                month -= 1
                if month == 0:
                    year, month = year - 1, 12
                allowed.add((year, month))
            if created.day in (1, 15) and (created.year, created.month) in allowed:
                decide(snapshot, "keep", "半月档保留过去 3 个自然月")
            else:
                decide(snapshot, "delete", "超出半月档 3 个自然月窗口")
        elif kind == "pre_change":
            ordered = sorted(
                [s for s in snapshots if s["kind"] == "pre_change" and s["created_at"]],
                key=lambda s: s["created_at"], reverse=True,
            )
            if snapshot in ordered[:2]:
                decide(snapshot, "keep", "升级前冷备保留最近 2 份")
            else:
                decide(snapshot, "delete", "升级前冷备只保留最近 2 份")
        else:
            decide(snapshot, "keep", "未知类型，保留")
    return decisions


def execute_prune(decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    executed = []
    for decision in decisions:
        if decision["action"] != "delete":
            continue
        path = Path(decision["snapshot"])
        if path.is_dir():
            shutil.rmtree(path)
            executed.append(decision)
    return executed


def plan_release_prune(root: Path) -> List[Dict[str, Any]]:
    """release 只按“最近 3 个 + 仍被引用”清理，绝不按数量删共享制品。"""
    root = Path(root)
    referenced = layout.collect_referenced_versions(root)
    versions = []
    for path in layout.releases_dir(root).iterdir() if layout.releases_dir(root).is_dir() else []:
        if not path.is_dir() or path.name.startswith("."):
            continue
        try:
            version = layout.normalize_version(path.name)
        except layout.LayoutError:
            continue
        versions.append((layout.version_tuple(version), version, path))
    versions.sort(reverse=True)
    decisions = []
    for index, (_, version, path) in enumerate(versions):
        if version in referenced:
            action, reason = "keep", "仍被指针/部署记录/回滚点引用"
        elif index < 3:
            action, reason = "keep", "最近 3 个 release"
        else:
            action, reason = "delete", "超出最近 3 个且无引用"
        decisions.append({
            "release": str(path), "version": version,
            "action": action, "reason": reason,
        })
    return decisions


def execute_release_prune(decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    executed = []
    for decision in decisions:
        if decision["action"] != "delete":
            continue
        path = Path(decision["release"])
        if path.is_dir():
            shutil.rmtree(path)
            executed.append(decision)
    return executed


def latest_snapshot(root: Path, env: str, *, kind: Optional[str] = None,
                    require_verified: bool = True) -> Optional[Path]:
    """按时间取最新快照；供 beta repair / 半月复制等“最近已验证”场景。"""
    snapshots = [s for s in list_snapshots(root, env, kind) if s["created_at"]]
    for snapshot in sorted(snapshots, key=lambda s: s["created_at"], reverse=True):
        if not require_verified:
            return snapshot["path"]
        if verify_snapshot(snapshot["path"])["ok"]:
            return snapshot["path"]
    return None
