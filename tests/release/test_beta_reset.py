"""beta 重建：prod 冷备、手机地址清理、独立凭据、fixture 骨架、repair 不碰 prod。"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from db import schema_guard
from deploy import release_layout as layout
from scripts import beta_reset
from tests.release.conftest import (
    init_data_root, make_release, tree_state,
)
from utils import backup as backup_mod
from utils.password_utils import verify_password

_ACCOUNT_RE = re.compile(r"^\s{2}(\S+)\s+\[(\w+)\]\s+(\S+)$")


def _prod_with_backup(root: Path):
    init_data_root(root, "prod")
    snapshot = backup_mod.create_backup(
        root, "prod", "pre_change", mode="cold", service_stopped=True,
        min_free_gib=0,
    )["snapshot"]
    make_release(root, "0.8.19.1")
    layout.switch_pointer(root, "beta", "0.8.19.1")
    return snapshot


def _parse_accounts(stdout: str):
    accounts = {}
    for line in stdout.splitlines():
        match = _ACCOUNT_RE.match(line)
        if match:
            accounts[match.group(1)] = (match.group(2), match.group(3))
    return accounts


def test_release_reset_isolated_credentials_and_fixture(tmp_path, capsys):
    root = tmp_path / "root"
    snapshot = _prod_with_backup(root)
    prod_state = tree_state(root / "data" / "prod")

    code = beta_reset.main([
        "--root", str(root), "--mode", "release",
        "--cold-backup", str(snapshot), "--prod-stopped",
        "--no-migrate", "--execute",
    ])
    assert code == 0
    output = capsys.readouterr().out
    accounts = _parse_accounts(output)
    assert set(accounts) == {"admin", "teacher"}
    assert accounts["admin"][0] == "super_admin"
    admin_password = accounts["admin"][1]
    teacher_password = accounts["teacher"][1]
    assert admin_password != teacher_password
    assert admin_password != "123456" and teacher_password != "123456"
    assert teacher_password.startswith("BETA-")

    beta_db = root / "data" / "beta" / "db" / "main.db"
    conn = sqlite3.connect(str(beta_db))
    try:
        rows = dict(conn.execute("SELECT name, password_hash FROM person"))
        mobile = conn.execute(
            "SELECT COUNT(*) FROM system_config WHERE config_key='mobile.base_url'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert verify_password(admin_password, rows["admin"])
    assert verify_password(teacher_password, rows["teacher"])
    assert mobile == 0, "beta 不得沿用生产手机地址"

    manifest_path = root / "data" / "beta" / "reset_manifest.json"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["passwords_recorded"] is False
    assert manifest["account_count"] == 2
    assert {item["name"] for item in manifest["accounts"]} == {"admin", "teacher"}
    for password in (admin_password, teacher_password):
        assert password not in manifest_text

    fixture = (root / "fixtures" / "beta_edge"
               / str(schema_guard.MAIN_SCHEMA_VERSION) / "seed.py")
    assert fixture.is_file(), "应生成版本化 fixture 骨架"
    assert (fixture.parent / "README.md").is_file()

    assert tree_state(root / "data" / "prod") == prod_state, "release 重置不得改 prod 数据"


def test_release_reset_requires_prod_stopped(tmp_path):
    root = tmp_path / "root"
    snapshot = _prod_with_backup(root)
    assert beta_reset.main([
        "--root", str(root), "--mode", "release",
        "--cold-backup", str(snapshot), "--execute",
    ]) == 2


def test_repair_uses_beta_snapshot_and_never_touches_prod(tmp_path):
    root = tmp_path / "root"
    prod_snapshot = _prod_with_backup(root)
    # 先用 prod 冷备重建一次 beta，再为 beta 生成快照做 repair
    assert beta_reset.main([
        "--root", str(root), "--mode", "release",
        "--cold-backup", str(prod_snapshot), "--prod-stopped",
        "--no-migrate", "--execute",
    ]) == 0
    beta_snapshot = backup_mod.create_backup(
        root, "beta", "daily", mode="hot", min_free_gib=0
    )["snapshot"]
    prod_state = tree_state(root / "data" / "prod")

    # repair 只接受 beta 快照
    assert beta_reset.main([
        "--root", str(root), "--mode", "repair",
        "--snapshot", str(prod_snapshot), "--no-migrate", "--execute",
    ]) == 2
    assert beta_reset.main([
        "--root", str(root), "--mode", "repair",
        "--snapshot", str(beta_snapshot), "--no-migrate", "--execute",
    ]) == 0
    assert tree_state(root / "data" / "prod") == prod_state


def test_repair_dry_run_does_not_write(tmp_path):
    root = tmp_path / "root"
    prod_snapshot = _prod_with_backup(root)
    assert beta_reset.main([
        "--root", str(root), "--mode", "release",
        "--cold-backup", str(prod_snapshot), "--prod-stopped",
        "--no-migrate", "--execute",
    ]) == 0
    beta_snapshot = backup_mod.create_backup(
        root, "beta", "daily", mode="hot", min_free_gib=0
    )["snapshot"]
    before = tree_state(root / "data" / "beta")
    assert beta_reset.main([
        "--root", str(root), "--mode", "repair", "--snapshot", str(beta_snapshot),
    ]) == 0
    assert tree_state(root / "data" / "beta") == before
