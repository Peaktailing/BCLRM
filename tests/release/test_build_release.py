"""build_release：制品必需文件、release.json 契约、版本禁复用、离线 wheelhouse。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from deploy import release_layout as layout
from scripts import build_release
from tests.release.conftest import PROJECT_ROOT


def _build(root: Path, version: str = "0.8.19.1", repo: Path = PROJECT_ROOT,
           extra=None):
    args = [
        "--root", str(root), "--repo", str(repo), "--version", version,
        "--sha", "HEAD", "--skip-venv", "--skip-wheelhouse", "--offline",
    ]
    return build_release.main(args + (extra or []))


def test_build_creates_immutable_payload(tmp_path, runtime_root):
    assert _build(runtime_root) == 0

    release = layout.release_dir(runtime_root, "0.8.19.1")
    payload = release / "payload"
    assert (payload / "docs" / "用户使用手册.md").is_file()
    assert (payload / ".streamlit" / "config.toml").is_file()
    assert any((payload / "assets").rglob("*"))
    assert (payload / "requirements.lock").is_file()
    assert not (payload / "release.json").exists(), "release.json 必须在 payload 外"
    assert not (payload / ".venv").exists()

    doc = json.loads((release / "release.json").read_text(encoding="utf-8"))
    assert set(doc) == set(layout.REQUIRED_RELEASE_FIELDS)
    assert "channel" not in doc, "渠道属于部署环境，不得写进不可变制品（D06）"
    assert doc["version"] == "0.8.19.1"
    assert len(doc["git_sha"]) == 40
    assert layout.payload_sha256(payload) == doc["artifact_sha256"]
    assert layout.hash_file(payload / "requirements.lock") == doc[
        "requirements_lock_sha256"
    ]
    assert doc["schema_versions"] == {
        "main.db": 2, "archive_cold.db": 1,
        "attach_cold.db": 1, "operation_log.db": 1,
    }

    index = json.loads(layout.releases_index_path(runtime_root).read_text("utf-8"))
    assert "0.8.19.1" in index["versions"]
    assert not list((runtime_root / "releases").glob(".build-*"))


def test_build_rejects_version_reuse(tmp_path, runtime_root):
    assert _build(runtime_root) == 0
    before = layout.payload_sha256(
        layout.release_dir(runtime_root, "0.8.19.1") / "payload"
    )
    assert _build(runtime_root) == 2
    after = layout.payload_sha256(
        layout.release_dir(runtime_root, "0.8.19.1") / "payload"
    )
    assert before == after, "复用拒绝不得改动已有 release"


def test_build_rejects_missing_required_tracked_files(tmp_path, runtime_root):
    repo = tmp_path / "bare-repo"
    repo.mkdir()
    (repo / "README.md").write_text("no manual", encoding="utf-8")
    env = dict(**__import__("os").environ)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
         "commit", "-qm", "init"],
        cwd=repo, check=True,
    )
    assert _build(runtime_root, repo=repo) == 2
    assert not layout.release_dir(runtime_root, "0.8.19.1").exists()


def test_collect_wheelhouse_offline_from_cache(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "streamlit-1.40.0-py3-none-any.whl").write_bytes(b"wheel")
    destination = tmp_path / "wheelhouse"
    report = build_release.collect_wheelhouse(
        "streamlit==1.40.0\n", destination, python=__import__("sys").executable,
        cache_sources=[cache], offline=True,
    )
    assert report["wheels"] == 1
    assert (destination / "streamlit-1.40.0-py3-none-any.whl").is_file()

    with pytest.raises(layout.ExecutionFailure) as excinfo:
        build_release.collect_wheelhouse(
            "streamlit==1.40.0\npandas==2.0.0\n", tmp_path / "other",
            python=__import__("sys").executable,
            cache_sources=[cache], offline=True,
        )
    assert "pandas" in str(excinfo.value)
