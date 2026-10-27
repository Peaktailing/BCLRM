"""备份/校验/恢复/保留策略：roundtrip、错误哈希、缺失附件、跨年保留。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from db import schema_guard
from deploy import release_layout as layout
from scripts import backup as backup_cli
from scripts import prune_backups, restore, verify_backup
from tests.release.conftest import add_attachment, tree_state
from utils import backup as backup_mod


def test_snapshot_layout_and_readonly_verify(snapshot: Path):
    assert snapshot.is_dir()
    assert (snapshot / "manifest.json").is_file()
    assert (snapshot / "data" / "db" / "main.db").is_file()
    assert (snapshot / "data" / "attachments.tar").is_file()
    assert (snapshot / "config" / "config.tar").is_file()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    for key in ("source", "created_at", "tool", "git_sha", "databases",
                "attachments", "schema_versions"):
        assert key in manifest
    assert manifest["source"]["mode"] == "cold"
    assert (manifest["databases"]["main.db"]["user_version"]
            == schema_guard.MAIN_SCHEMA_VERSION)
    assert manifest["databases"]["main.db"]["row_counts"]["person"] == 2
    assert manifest["attachments"]["file_count"] == 1
    assert manifest["attachments"]["missing"] == []

    before = tree_state(snapshot)
    report = backup_mod.verify_snapshot(snapshot)
    after = tree_state(snapshot)
    assert report["ok"], report["errors"]
    assert before == after, "verify 必须只读，不得改动快照"


def test_restore_roundtrip(prod_root, snapshot):
    target = prod_root / "data" / "prod" / "restored"
    code = restore.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--env", "prod", "--target", str(target),
        "--confirm-prod", "--service-stopped", "--execute",
    ])
    assert code == 0
    assert (target / "db" / "main.db").is_file()
    assert (target / "attachments" / "msds" / "abc123_msds.pdf").is_file()
    # 快照内的数据库已统一为 DELETE journal 模式，而生产中仍可能是 WAL，
    # 原始字节不可直接比较；以“快照与还原副本字节一致 + 逻辑校验一致”为准。
    source_db = snapshot / "data" / "db" / "main.db"
    restored_db = target / "db" / "main.db"
    assert layout.hash_file(restored_db) == layout.hash_file(source_db)
    report = backup_mod.verify_snapshot(snapshot)
    assert report["ok"], report["errors"]
    conn = backup_mod._open_readonly(restored_db)
    try:
        assert backup_mod._user_version(conn) == schema_guard.MAIN_SCHEMA_VERSION
        assert backup_mod._integrity_ok(conn)
    finally:
        conn.close()


def test_restore_requires_prod_confirmations(prod_root, snapshot):
    target = prod_root / "data" / "prod" / "restored2"
    code = restore.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--env", "prod", "--target", str(target), "--execute",
    ])
    assert code == 2
    assert not target.exists()

    code = restore.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--env", "prod", "--target", str(target),
        "--confirm-prod", "--execute",
    ])
    assert code == 2


def test_restore_rejects_target_outside_env(prod_root, snapshot, tmp_path):
    outside = tmp_path / "outside"
    code = restore.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--env", "prod", "--target", str(outside),
        "--confirm-prod", "--service-stopped", "--execute",
    ])
    assert code == 2
    assert not outside.exists()

    relative = restore.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--env", "beta", "--target", "relative/path", "--execute",
    ])
    assert relative == 2


def test_wrong_hash_is_rejected(prod_root, snapshot, tmp_path):
    broken = tmp_path / "broken-snapshot"
    shutil.copytree(snapshot, broken)
    db = broken / "data" / "db" / "main.db"
    data = bytearray(db.read_bytes())
    data[-10] ^= 0xFF
    db.write_bytes(bytes(data))

    report = backup_mod.verify_snapshot(broken)
    assert not report["ok"]
    assert any("sha256" in error for error in report["errors"])
    assert verify_backup.main([str(broken)]) == 2


def test_missing_attachment_refuses_backup(prod_root):
    (prod_root / "data" / "prod" / "attachments" / "msds" / "abc123_msds.pdf").unlink()
    with pytest.raises(backup_mod.BackupError) as excinfo:
        backup_mod.create_backup(
            prod_root, "prod", "daily", mode="hot", min_free_gib=0
        )
    assert "缺失" in str(excinfo.value)


def test_orphan_attachment_is_allowed(prod_root):
    extra = prod_root / "data" / "prod" / "attachments" / "msds" / "orphan.pdf"
    extra.write_bytes(b"orphan")
    result = backup_mod.create_backup(
        prod_root, "prod", "daily", mode="hot", min_free_gib=0
    )
    manifest = result["manifest"]
    assert manifest["attachments"]["orphan_count"] == 1
    assert "msds/orphan.pdf" in manifest["attachments"]["orphans"]
    assert result["verification"]["ok"]


def test_cold_backup_requires_service_stopped(prod_root):
    code = backup_cli.main([
        "--root", str(prod_root), "--env", "prod", "--kind", "pre_change",
        "--mode", "cold",
    ])
    assert code == 2


def test_restore_replace_keeps_old_directory(prod_root, snapshot):
    target = prod_root / "data" / "prod" / "rehearsal"
    args = [
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--env", "prod", "--target", str(target),
        "--confirm-prod", "--service-stopped", "--replace", "--execute",
    ]
    assert restore.main(args) == 0
    result = backup_mod.restore_snapshot(snapshot, target, replace=True)
    assert result["replaced_from"]
    assert Path(result["replaced_from"]).is_dir()


def _fake_snapshot(root: Path, env: str, kind: str, name: str,
                   created_at: str) -> Path:
    path = layout.backups_dir(root, env) / kind / name
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(
        json.dumps({"created_at": created_at}), encoding="utf-8"
    )
    return path


def test_prune_retention_cross_year(prod_root):
    root = prod_root
    daily = layout.backups_dir(root, "prod") / "daily"
    # 2027-01-10 为“今天”：最近 7 天从 01-04 起
    for name, date in [
        ("d-0104", "2027-01-04T02:15:00+00:00"),
        ("d-0103", "2027-01-03T02:15:00+00:00"),
        ("d-0101", "2027-01-01T02:15:00+00:00"),
        ("d-1231", "2026-12-31T02:15:00+00:00"),
    ]:
        _fake_snapshot(root, "prod", "daily", name, date)

    for name, date, keep in [
        ("sm-2026-10-15", "2026-10-15T02:45:00+00:00", False),
        ("sm-2026-11-15", "2026-11-15T02:45:00+00:00", True),
        ("sm-2026-12-01", "2026-12-01T02:45:00+00:00", True),
        ("sm-2026-12-15", "2026-12-15T02:45:00+00:00", True),
        ("sm-2027-01-01", "2027-01-01T02:45:00+00:00", True),
        ("sm-2026-12-31", "2026-12-31T02:45:00+00:00", False),
    ]:
        _fake_snapshot(root, "prod", "semimonthly", name, date)

    pc1 = _fake_snapshot(root, "prod", "pre_change", "pc-1", "2027-01-01T00:00:00+00:00")
    _fake_snapshot(root, "prod", "pre_change", "pc-2", "2027-01-05T00:00:00+00:00")
    _fake_snapshot(root, "prod", "pre_change", "pc-3", "2027-01-08T00:00:00+00:00")
    _fake_snapshot(root, "prod", "pre_change", "pc-4", "2027-01-09T00:00:00+00:00")
    _fake_snapshot(root, "prod", "annual", "annual-2020", "2020-01-01T03:30:00+00:00")

    layout.write_json_atomic(layout.deployment_file(root, "prod"), {
        "version": "0.8.18.1",
        "rollback_snapshot": str(pc1),
    })

    now = datetime(2027, 1, 10, 12, 0, tzinfo=timezone.utc)
    decisions = backup_mod.plan_prune(root, "prod", now=now)
    by_name = {item["name"]: item for item in decisions}

    assert by_name["d-0104"]["action"] == "keep"
    assert by_name["d-0103"]["action"] == "delete"
    assert by_name["d-1231"]["action"] == "delete"
    assert by_name["sm-2026-10-15"]["action"] == "delete"
    assert by_name["sm-2026-11-15"]["action"] == "keep"
    assert by_name["sm-2027-01-01"]["action"] == "keep"
    assert by_name["sm-2026-12-31"]["action"] == "delete"
    assert by_name["pc-4"]["action"] == "keep"
    assert by_name["pc-3"]["action"] == "keep"
    assert by_name["pc-1"]["action"] == "keep", "当前回滚点不得删除"
    assert "回滚" in by_name["pc-1"]["reason"]
    assert by_name["annual-2020"]["action"] == "keep"

    executed = backup_mod.execute_prune(decisions)
    assert executed
    assert not (daily / "d-1231").exists()
    assert (daily / "d-0104").exists()
    assert pc1.is_dir()


def test_prune_beta_keeps_two(prod_root):
    for index, date in enumerate((
        "2027-01-01T00:00:00+00:00",
        "2027-01-02T00:00:00+00:00",
        "2027-01-03T00:00:00+00:00",
    )):
        _fake_snapshot(prod_root, "beta", "daily", f"b-{index}", date)
    decisions = backup_mod.plan_prune(
        prod_root, "beta", now=datetime(2027, 1, 10, tzinfo=timezone.utc)
    )
    actions = {item["name"]: item["action"] for item in decisions}
    assert actions == {"b-0": "delete", "b-1": "keep", "b-2": "keep"}


def test_release_prune_keeps_referenced(prod_root):
    for index in range(1, 6):
        version = f"0.8.19.{index}"
        release = layout.release_dir(prod_root, version)
        release.mkdir(parents=True)
        (release / "release.json").write_text("{}", encoding="utf-8")
    layout.write_json_atomic(layout.releases_index_path(prod_root), {
        "schema_version": 1,
        "versions": {
            f"0.8.19.{index}": {"git_sha": "a" * 40} for index in range(1, 6)
        },
    })
    layout.switch_pointer(prod_root, "prod", "0.8.19.2")
    layout.switch_pointer(prod_root, "beta", "0.8.19.5")
    layout.write_json_atomic(layout.deployment_file(prod_root, "prod"), {
        "version": "0.8.19.2", "rollback_release": "0.8.19.4",
    })
    decisions = backup_mod.plan_release_prune(prod_root)
    actions = {item["version"]: item["action"] for item in decisions}
    assert actions["0.8.19.1"] == "delete"
    assert actions["0.8.19.2"] == "keep", "指针引用必须保留"
    assert actions["0.8.19.4"] == "keep", "回滚点引用必须保留"
    assert actions["0.8.19.5"] == "keep"
    backup_mod.execute_release_prune(decisions)
    assert not layout.release_dir(prod_root, "0.8.19.1").exists()
    assert layout.release_dir(prod_root, "0.8.19.2").is_dir()
    # 台账仍保留版本号：目录删除不等于允许复用
    assert "0.8.19.1" in layout.load_index(prod_root)["versions"]


def test_clone_and_second_copy(prod_root, snapshot, tmp_path):
    cloned = backup_mod.clone_snapshot(
        snapshot, prod_root, "prod", "semimonthly",
        now=datetime(2027, 1, 15, 2, 45, tzinfo=timezone.utc),
    )
    assert cloned["verification"]["ok"]
    assert Path(cloned["snapshot"]).parent.name == "semimonthly"

    second = tmp_path / "media"
    second.mkdir()
    copied = backup_mod.copy_to_second_location(
        Path(cloned["snapshot"]), second, "prod"
    )
    assert copied["verification"]["ok"]
    assert Path(copied["target"]).is_dir()
    assert (Path(copied["target"]) / "manifest.json").is_file()


def test_prune_cli_defaults_to_dry_run(prod_root, snapshot, capsys):
    before = snapshot.exists()
    code = prune_backups.main(["--root", str(prod_root), "--env", "prod"])
    assert code == 0
    assert before and snapshot.exists()
    assert "DRY-RUN" in capsys.readouterr().out
