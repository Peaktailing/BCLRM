"""rehearse_upgrade：临时目录恢复、备用端口、runtime_cli 迁移/冒烟、报告。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from deploy import release_layout as layout
from scripts import rehearse_upgrade
from tests.release.conftest import make_release, tree_state


def test_rehearsal_runs_migrate_and_smoke_without_server(prod_root, snapshot, tmp_path):
    release = make_release(prod_root, "0.8.19.1")
    report_path = tmp_path / "rehearsal.json"
    before = tree_state(snapshot)

    code = rehearse_upgrade.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--release", str(release), "--no-server", "--python",
        os.sys.executable, "--report", str(report_path),
    ])
    assert code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["version"] == "0.8.19.1"
    assert report["port"] is None
    assert [step["step"] for step in report["steps"]] == [
        "check(before migrate)", "migrate", "check(after migrate)", "smoke",
    ]
    assert all(step["returncode"] == 0 for step in report["steps"])
    assert tree_state(snapshot) == before, "演练不得改动快照"
    assert not Path(report["workspace"]).exists(), "默认清理临时恢复目录"


def test_rehearsal_refuses_production_ports(prod_root, snapshot):
    release = make_release(prod_root, "0.8.19.1")
    assert rehearse_upgrade.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--release", str(release), "--no-server", "--port-start", "8501",
    ]) == 2


def test_find_free_port_skips_pinned_ports():
    port = layout.find_free_port(8501)
    assert port not in (8501, 8601)
    assert port >= 8502


def test_rehearsal_cleans_up_on_failed_migrate(prod_root, snapshot):
    release = make_release(prod_root, "0.8.19.1", schema={
        "main.db": 3, "archive_cold.db": 2,
        "attach_cold.db": 2, "operation_log.db": 2,
    })
    report_path = prod_root / "logs" / "rehearsals" / "failed.json"
    code = rehearse_upgrade.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--release", str(release), "--no-server", "--report", str(report_path),
    ])
    assert code == 3
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert not Path(report["workspace"]).exists()


@pytest.mark.skipif(
    os.environ.get("BCLRM_RUN_SERVER_TESTS") != "1",
    reason="需要真实 Streamlit 端口启动；默认跳过，Stage 0C 本机演练开启",
)
def test_rehearsal_with_real_server_on_spare_port(prod_root, snapshot):
    release = make_release(prod_root, "0.8.19.1")
    code = rehearse_upgrade.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--release", str(release), "--port-start", "8790",
        "--health-timeout", "120",
    ])
    assert code == 0


def test_rehearsal_defaults_to_current_env_pointer(prod_root, snapshot):
    """定时任务不写版本：默认演练 current_prod 指向的 release。"""
    release = make_release(prod_root, "0.8.19.2")
    layout.switch_pointer(prod_root, "prod", "0.8.19.2")
    report_path = prod_root / "logs" / "rehearsals" / "pointer.json"
    code = rehearse_upgrade.main([
        "--root", str(prod_root), "--snapshot", str(snapshot),
        "--no-server", "--report", str(report_path), "--json",
    ])
    assert code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["version"] == "0.8.19.2"
    assert Path(report["release"]) == release.resolve()


def test_rehearsal_without_pointer_or_release_fails(prod_root, snapshot):
    with pytest.raises(SystemExit) as exc:
        rehearse_upgrade.main([
            "--root", str(prod_root), "--snapshot", str(snapshot), "--no-server",
        ])
    assert exc.value.code == 2
