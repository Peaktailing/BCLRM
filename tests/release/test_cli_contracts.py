"""CLI 契约：--help、退出码、禁止通用 --force、系统系统 unit 关键字段。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.release.conftest import PROJECT_ROOT

SCRIPTS = (
    "build_release.py", "backup.py", "restore.py", "verify_backup.py",
    "prune_backups.py", "rehearse_upgrade.py", "beta_reset.py",
    "deploy_prod.py", "rollback_prod.py", "release_status.py",
)


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_cli_has_help(script):
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script), "--help"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--root" in result.stdout or script == "verify_backup.py"


def test_destructive_cli_defaults_to_dry_run(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    from scripts import deploy_prod, prune_backups, restore

    # 无快照也能在 dry-run 前被参数/预检拦下，绝不写生产
    assert prune_backups.main(["--root", str(root), "--env", "prod"]) == 0
    assert restore.main([
        "--root", str(root), "--snapshot", str(root / "nope"),
        "--env", "beta", "--target", str(root / "data" / "beta" / "x"),
    ]) == 2


def test_no_generic_force_switch():
    for name in ("restore.py", "deploy_prod.py", "rollback_prod.py", "beta_reset.py"):
        text = (PROJECT_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert '"--force"' not in text
        assert "'--force'" not in text


def test_build_rejects_three_part_version(tmp_path):
    from scripts import build_release
    assert build_release.main([
        "--root", str(tmp_path), "--version", "0.8.19",
        "--skip-venv", "--skip-wheelhouse",
    ]) == 2


def test_verify_missing_snapshot_exit_2(tmp_path):
    from scripts import verify_backup
    assert verify_backup.main(["--snapshot", str(tmp_path / "missing")]) == 2


def test_systemd_units_are_loopback_and_user_level():
    unit_dir = PROJECT_ROOT / "systemd" / "user"
    prod = (unit_dir / "bclrm-prod.service").read_text(encoding="utf-8")
    beta = (unit_dir / "bclrm-beta.service").read_text(encoding="utf-8")
    assert "--server.port 8501" in prod and "--server.address 127.0.0.1" in prod
    assert "--server.port 8601" in beta and "--server.address 127.0.0.1" in beta
    for text in (prod, beta):
        assert "EnvironmentFile=-/home/biochm/BCLRM/env/" in text
        assert "Restart=always" in text
        assert "TimeoutStopSec=30" in text
        assert "/home/biochm/BCLRM/current_" in text
        assert ".venv/bin/python" in text
        assert "0.0.0.0" not in text
    assert (unit_dir / "bclrm-maintenance.timer").is_file()
    maintenance = (unit_dir / "bclrm-maintenance.service").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 05:00:00" in (
        unit_dir / "bclrm-maintenance.timer"
    ).read_text(encoding="utf-8")
    assert "daily_maintenance.py" in maintenance
    assert "ExecStopPost=" in maintenance
    assert "backup.py" not in maintenance  # 编排由脚本负责，unit 不直接清表/备份
    assert (unit_dir / "bclrm-backup-annual.timer").is_file()
