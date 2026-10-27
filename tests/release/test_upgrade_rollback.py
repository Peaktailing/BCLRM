"""prod 部署、故障自动回滚、常规回滚与 legacy 占位路径。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from deploy import release_layout as layout
from scripts import deploy_prod, rollback_prod
from tests.release.conftest import (
    init_data_root, make_release, write_acceptance, write_rehearsal_report,
)
from utils import backup as backup_mod


def _prepare(root: Path, target_version: str = "0.8.19.1",
             schema=None):
    init_data_root(root, "prod")
    # 部署预检要求已有“坏一台能退回去”的已验证快照；测试同样从真实备份开始。
    backup_mod.create_backup(root, "prod", "daily", mode="hot",
                             source="test", min_free_gib=0)
    old = make_release(root, "0.8.18.1")
    layout.switch_pointer(root, "prod", "0.8.18.1")
    target = make_release(root, target_version, schema=schema)
    layout.switch_pointer(root, "beta", target_version)
    write_acceptance(root, target_version)
    write_rehearsal_report(root, target_version)
    return old, target


def _deploy(root: Path, version: str):
    return deploy_prod.main([
        "--root", str(root), "--version", version, "--execute",
        "--no-systemd", "--skip-http-health", "--min-free-gib", "0",
    ])


def _user_version(db: Path) -> int:
    conn = sqlite3.connect(str(db))
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def test_deploy_success_switches_pointer_and_records(tmp_path):
    root = tmp_path / "root"
    old, target = _prepare(root)
    assert _deploy(root, "0.8.19.1") == 0

    assert layout.read_pointer(root, "prod") == target.resolve()
    record = layout.load_deployment(root, "prod")
    assert record["status"] == "deployed"
    assert record["version"] == "0.8.19.1"
    assert record["previous"]["version"] == "0.8.18.1"
    snapshot = Path(record["backup"]["path"])
    assert snapshot.is_dir()
    assert backup_mod.verify_snapshot(snapshot)["ok"]
    assert json.loads((target / "release.json").read_text("utf-8"))["version"] == "0.8.19.1"
    assert old.is_dir(), "旧 release 必须保留供回滚"


def test_deploy_failure_restores_snapshot_and_pointer(tmp_path):
    root = tmp_path / "root"
    old, _ = _prepare(root, schema={
        "main.db": 3, "archive_cold.db": 1,
        "attach_cold.db": 1, "operation_log.db": 1,
    })
    assert _deploy(root, "0.8.19.1") == 3

    prod = layout.read_pointer(root, "prod")
    assert prod == old.resolve(), "失败后必须切回旧 release"
    record = layout.load_deployment(root, "prod")
    assert record["status"] == "rolled_back_failed_deploy"
    assert record["failure"]["restore_ok"] is True
    assert record["failure"]["switch_back_ok"] is True
    main_db = root / "data" / "prod" / "db" / "main.db"
    assert _user_version(main_db) == 2
    conn = sqlite3.connect(str(main_db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM person").fetchone()[0] == 2
    finally:
        conn.close()


def test_half_migrated_ledger_blocks_backup_and_deploy(tmp_path):
    root = tmp_path / "root"
    _prepare(root)
    main_db = root / "data" / "prod" / "db" / "main.db"
    conn = sqlite3.connect(str(main_db))
    try:
        conn.execute(
            "INSERT INTO schema_migrations(id, db_name, status, target_version, "
            "started_at) VALUES ('half', 'main.db', 'running', 2, '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()

    try:
        backup_mod.create_backup(root, "prod", "pre_change", mode="cold",
                                 service_stopped=True, min_free_gib=0)
    except backup_mod.BackupError as exc:
        assert "running" in str(exc)
    else:
        raise AssertionError("半程迁移台账必须拒绝备份")

    assert _deploy(root, "0.8.19.1") == 3
    assert layout.read_pointer(root, "prod").name == "0.8.18.1"
    status = layout.load_deployment(root, "prod")
    assert status["status"] != "deployed"


def test_deploy_preflight_requires_rehearsal(tmp_path):
    root = tmp_path / "root"
    init_data_root(root, "prod")
    make_release(root, "0.8.18.1")
    layout.switch_pointer(root, "prod", "0.8.18.1")
    make_release(root, "0.8.19.1")
    layout.switch_pointer(root, "beta", "0.8.19.1")
    write_acceptance(root, "0.8.19.1")
    # 不写演练报告
    assert _deploy(root, "0.8.19.1") == 2
    assert layout.read_pointer(root, "prod").name == "0.8.18.1"


def test_deploy_preflight_rejects_beta_mismatch(tmp_path):
    root = tmp_path / "root"
    init_data_root(root, "prod")
    make_release(root, "0.8.18.1")
    layout.switch_pointer(root, "prod", "0.8.18.1")
    make_release(root, "0.8.19.1")
    make_release(root, "0.8.19.2")
    layout.switch_pointer(root, "beta", "0.8.19.2")
    write_acceptance(root, "0.8.19.1")
    write_rehearsal_report(root, "0.8.19.1")
    assert _deploy(root, "0.8.19.1") == 2


def test_rollback_uses_deployment_snapshot(tmp_path):
    root = tmp_path / "root"
    old, _ = _prepare(root)
    assert _deploy(root, "0.8.19.1") == 0
    assert layout.read_pointer(root, "prod").name == "0.8.19.1"

    assert rollback_prod.main([
        "--root", str(root), "--confirm-prod", "--service-stopped",
        "--execute", "--no-systemd", "--skip-http-health",
    ]) == 0
    assert layout.read_pointer(root, "prod") == old.resolve()
    record = layout.load_deployment(root, "prod")
    assert record["status"] == "rolled_back"
    assert record["version"] == "0.8.18.1"
    assert _user_version(root / "data" / "prod" / "db" / "main.db") == 2


def test_rollback_requires_two_prod_switches(tmp_path):
    root = tmp_path / "root"
    _prepare(root)
    assert rollback_prod.main(["--root", str(root), "--execute",
                               "--no-systemd"]) == 2
    assert rollback_prod.main([
        "--root", str(root), "--execute", "--confirm-prod", "--no-systemd",
    ]) == 2


def test_legacy_rollback_placeholder_never_creates_directory(tmp_path):
    root = tmp_path / "root"
    init_data_root(root, "prod")
    snapshot = backup_mod.create_backup(
        root, "prod", "pre_change", mode="cold", service_stopped=True,
        min_free_gib=0,
    )["snapshot"]
    legacy = root / "legacy" / "prod-deadbeef"
    missing = rollback_prod.main([
        "--root", str(root), "--legacy", str(legacy), "--snapshot", snapshot,
        "--confirm-prod", "--service-stopped", "--execute",
        "--no-systemd", "--skip-http-health",
    ])
    assert missing == 2
    assert not legacy.exists(), "legacy 目录只能由 Stage 2 创建"

    legacy.mkdir(parents=True)
    (legacy / "README.txt").write_text("legacy code", encoding="utf-8")
    layout.write_json_atomic(legacy / "legacy_manifest.json", {
        "git_sha": "c" * 40,
        "created_at": layout.utc_now_iso(),
        "source_path": "/home/biochm/Reagent-manager",
    })
    code = rollback_prod.main([
        "--root", str(root), "--legacy", str(legacy), "--snapshot", snapshot,
        "--confirm-prod", "--service-stopped", "--execute",
        "--no-systemd", "--skip-http-health",
    ])
    assert code == 0
    assert (legacy / "db" / "main.db").is_file()
    assert (legacy / "README.txt").read_text(encoding="utf-8") == "legacy code"
    assert layout.load_deployment(root, "prod")["status"] == "legacy_rolled_back"
