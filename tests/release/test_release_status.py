"""release_status：四整数比较、两轨门禁、观察期、祖先关系与版本禁复用。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from deploy import release_layout as layout
from scripts import release_status
from tests.release.conftest import (
    PROJECT_ROOT, init_data_root, make_release, write_acceptance,
)


def test_status_gates_and_observation(tmp_path):
    root = tmp_path / "root"
    init_data_root(root, "prod")
    make_release(root, "0.8.19.9")
    layout.switch_pointer(root, "prod", "0.8.19.9")
    make_release(root, "0.8.19.10")
    layout.switch_pointer(root, "beta", "0.8.19.10")
    write_acceptance(root, "0.8.19.10", waived=False)
    deployed_at = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    layout.write_json_atomic(layout.deployment_file(root, "beta"), {
        "version": "0.8.19.10", "deployed_at": deployed_at, "status": "deployed",
    })

    status = release_status.collect_status(
        root, PROJECT_ROOT, verify_artifacts=True, observation_days=3
    )
    assert status["ok"], status["warnings"]
    assert status["gates"]["prod_lt_beta"] is True
    assert status["gates"]["merge_base_ancestor"] is True
    assert status["observation"]["ready"] is True
    assert status["prod"]["artifact_verified"] is True
    # 0.8.19.10 必须大于 0.8.19.9（四整数，不是字符串）
    assert layout.version_tuple("0.8.19.10") > layout.version_tuple("0.8.19.9")

    assert release_status.main([
        "--root", str(root), "--check", "--verify-artifacts",
    ]) == 0


def test_status_check_fails_when_prod_not_lower(tmp_path):
    root = tmp_path / "root"
    init_data_root(root, "prod")
    make_release(root, "0.8.19.10")
    layout.switch_pointer(root, "prod", "0.8.19.10")
    make_release(root, "0.8.19.9")
    layout.switch_pointer(root, "beta", "0.8.19.9")

    status = release_status.collect_status(
        root, PROJECT_ROOT, verify_artifacts=False, observation_days=3
    )
    assert status["ok"] is False
    assert status["gates"]["prod_lt_beta"] is False
    assert release_status.main(["--root", str(root), "--check"]) == 2


def test_status_tolerates_missing_beta(tmp_path):
    root = tmp_path / "root"
    init_data_root(root, "prod")
    make_release(root, "0.8.19.9")
    layout.switch_pointer(root, "prod", "0.8.19.9")
    status = release_status.collect_status(
        root, PROJECT_ROOT, verify_artifacts=False, observation_days=3
    )
    assert status["prod"]["version"] == "0.8.19.9"
    assert status["beta"]["version"] is None


def test_version_reuse_rejected_even_after_directory_pruned(tmp_path):
    root = tmp_path / "root"
    init_data_root(root, "prod")
    release = make_release(root, "0.8.19.9")
    with pytest.raises(layout.LayoutError):
        layout.reject_version_reuse(root, "0.8.19.9")

    # 模拟保留策略删目录，但台账仍在：仍然禁止复用
    import shutil
    shutil.rmtree(release)
    with pytest.raises(layout.LayoutError):
        layout.reject_version_reuse(root, "0.8.19.9")
