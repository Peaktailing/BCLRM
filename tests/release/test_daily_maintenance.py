"""每日维护编排：代码 bundle、清单、保留与预检（不触碰真实部署根）。"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy import release_layout as layout
from scripts import daily_maintenance


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True, text=True, check=True,
    )


@pytest.fixture()
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    (path / "app.py").write_text("print('v1')\n", encoding="utf-8")
    _git(path, "add", "app.py")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _maintenance(tmp_path: Path, repo: Path, *,
                 skip_offsite: bool = True) -> daily_maintenance.Maintenance:
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    args = SimpleNamespace(
        root=str(root), unit="fake.service", port=18999,
        code_repo=str(repo), code_dir=str(code_dir),
        systemctl="systemctl --user", skip_offsite=skip_offsite,
        execute=True,
    )
    return daily_maintenance.Maintenance(args)


def test_code_backup_creates_verified_bundle(tmp_path, repo):
    maintenance = _maintenance(tmp_path, repo)
    maintenance.code_backup()

    bundles = list((tmp_path / "code").glob("BCLRM-*.bundle"))
    assert len(bundles) == 1
    meta = json.loads(bundles[0].with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["head"] == _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert meta["dirty"] is False
    assert maintenance.steps[-1]["name"] == "code-backup"
    assert maintenance.steps[-1]["ok"] is True

    verify = subprocess.run(
        ["git", "-C", str(repo), "bundle", "verify", str(bundles[0])],
        capture_output=True, text=True,
    )
    assert verify.returncode == 0


def test_code_backup_records_uncommitted_patch(tmp_path, repo):
    maintenance = _maintenance(tmp_path, repo)
    (repo / "app.py").write_text("print('v2')\n", encoding="utf-8")
    maintenance.code_backup()

    bundle = next((tmp_path / "code").glob("BCLRM-*.bundle"))
    patch = bundle.with_suffix(".patch")
    assert patch.is_file()
    assert "print('v2')" in patch.read_text(encoding="utf-8")
    meta = json.loads(bundle.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["dirty"] is True
    assert meta["uncommitted_patch"] == patch.name


def test_prune_code_keeps_newest_two_and_three_month_window(tmp_path, repo):
    maintenance = _maintenance(tmp_path, repo)
    code_dir = Path(maintenance.code_dir)
    old = 0
    files = []
    for index in range(5):
        bundle = code_dir / f"BCLRM-2026010{index}T000000Z-abcdef{index}.bundle"
        bundle.write_text("x", encoding="utf-8")
        bundle.with_suffix(".json").write_text("{}", encoding="utf-8")
        if index < 3:
            os.utime(bundle, (old, old))
        files.append(bundle)
    maintenance.prune_code()
    remaining = set(code_dir.glob("BCLRM-*.bundle"))
    assert files[3] in remaining and files[4] in remaining
    assert files[0] not in remaining


def test_dry_run_requires_copy_preflight(tmp_path, repo):
    root = tmp_path / "empty-root"
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    result = daily_maintenance.main([
        "--root", str(root), "--code-repo", str(repo),
        "--code-dir", str(code_dir),
    ])
    assert result == 2


def test_dry_run_plan_when_preflight_passes(tmp_path, repo):
    root = tmp_path / "root"
    (root / "data" / "prod" / "db").mkdir(parents=True)
    (root / "data" / "prod" / "db" / "main.db").write_text("", encoding="utf-8")
    python = root / "current_prod" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    scripts = root / "current_prod" / "payload" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("backup.py", "verify_backup.py", "prune_backups.py"):
        (scripts / name).write_text("", encoding="utf-8")
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    fake_systemctl = tmp_path / "systemctl"
    fake_systemctl.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
    fake_systemctl.chmod(0o755)

    result = daily_maintenance.main([
        "--root", str(root), "--code-repo", str(repo),
        "--code-dir", str(code_dir), "--systemctl", str(fake_systemctl),
    ])
    assert result == 0


def test_restart_service_requires_health(monkeypatch, tmp_path):
    maintenance = _maintenance(tmp_path, Path(tmp_path / "repo"))
    calls = []

    class Result:
        returncode = 0
        stderr = ""

    def fake_systemctl(verb, *extra):
        calls.append((verb, *extra))

        return Result()

    monkeypatch.setattr(maintenance, "_systemctl_run", fake_systemctl)
    monkeypatch.setattr(maintenance, "health_ok", lambda: True)
    assert maintenance.restart_service() is True
    assert calls == [("start", "fake.service")]
    assert maintenance.restart["ok"] is True


def test_stop_service_waits_for_inactive_and_port(monkeypatch, tmp_path):
    maintenance = _maintenance(tmp_path, Path(tmp_path / "repo"))
    state = {"active": True, "port": True}

    class Result:
        returncode = 0
        stderr = ""

    def fake_systemctl(verb, *extra):
        if verb == "stop":
            state["active"] = False
            state["port"] = False

        return Result()

    monkeypatch.setattr(maintenance, "_systemctl_run", fake_systemctl)
    monkeypatch.setattr(maintenance, "service_active", lambda: state["active"])
    monkeypatch.setattr(maintenance, "port_open", lambda: state["port"])
    maintenance.stop_service()
    assert maintenance.steps[-1]["name"] == "stop-prod"
    assert maintenance.steps[-1]["ok"] is True

    root = tmp_path / "root"
    (root / "backups").mkdir(parents=True)
    volume = tmp_path / "vault"
    volume.mkdir()
    monkeypatch.setattr(layout, "DEFAULT_ROOT", root)
    monkeypatch.setattr(layout, "BACKUP_VOLUME", volume)
    monkeypatch.setattr(layout.os.path, "ismount", lambda path: False)
    with pytest.raises(layout.LayoutError):
        layout.ensure_backup_volume(root)


def test_ensure_backup_volume_requires_symlink_into_vault(monkeypatch, tmp_path):
    root = tmp_path / "root"
    (root / "backups").mkdir(parents=True)
    volume = tmp_path / "vault"
    (volume / "backups").mkdir(parents=True)
    monkeypatch.setattr(layout, "DEFAULT_ROOT", root)
    monkeypatch.setattr(layout, "BACKUP_VOLUME", volume)
    monkeypatch.setattr(layout.os.path, "ismount", lambda path: True)
    with pytest.raises(layout.LayoutError):
        layout.ensure_backup_volume(root)
    (root / "backups").rmdir()
    (root / "backups").symlink_to(volume / "backups")
    layout.ensure_backup_volume(root)
