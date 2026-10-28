"""异地归档备份：上传、幂等、清单、保留镜像与防误删。"""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from deploy import offsite


def _make_snapshot(root: Path, env: str, kind: str, name: str,
                   payload: str = "db-bytes") -> Path:
    snap = root / "backups" / env / kind / name
    (snap / "data" / "db").mkdir(parents=True)
    (snap / "manifest.json").write_text(
        json.dumps({"created_at": name, "databases": {}, "checks": {}}),
        encoding="utf-8",
    )
    (snap / "data" / "db" / "main.db").write_text(payload, encoding="utf-8")
    return snap


@pytest.fixture()
def roots(tmp_path):
    root = tmp_path / "root"
    remote = tmp_path / "remote"
    remote.mkdir()
    return root, remote


def test_upload_archive_and_single_manifest(roots):
    root, remote = roots
    _make_snapshot(root, "prod", "daily", "20260101T000000Z-a")
    _make_snapshot(root, "prod", "daily", "20260102T000000Z-b")

    result = offsite.sync(root, ["prod"], offsite.LocalRemote(remote),
                          tmp_path_for_archive(tmp_path=root))
    assert result["ok"] and len(result["uploaded"]) == 2
    archive = remote / "prod/daily/20260102T000000Z-b.tar.gz"
    assert archive.is_file()
    with tarfile.open(archive, "r:gz") as tar:
        assert "20260102T000000Z-b/manifest.json" in tar.getnames()

    sums = (remote / offsite.SUMS_NAME).read_text(encoding="utf-8")
    assert "prod/daily/20260101T000000Z-a.tar.gz" in sums
    assert "prod/daily/20260102T000000Z-b.tar.gz" in sums
    assert len(sums.strip().splitlines()) == 2
    # 清单必须能被 sha256sum 的裸格式直接消费
    for line in sums.strip().splitlines():
        digest, rel = line.split("  ", 1)
        assert len(digest) == 64
        assert (remote / rel).is_file()
    assert not list((root / "tmp").glob("*.tar.gz"))


def tmp_path_for_archive(tmp_path: Path) -> Path:
    return Path(tmp_path) / "tmp"


def test_second_run_is_idempotent(roots):
    root, remote = roots
    _make_snapshot(root, "prod", "daily", "20260101T000000Z-a")
    remote_impl = offsite.LocalRemote(remote)
    first = offsite.sync(root, ["prod"], remote_impl,
                         tmp_path_for_archive(tmp_path=root))
    assert first["uploaded"]
    second = offsite.sync(root, ["prod"], remote_impl,
                          tmp_path_for_archive(tmp_path=root))
    assert second["uploaded"] == []
    assert second["manifest_entries"] == 1


def test_prune_mirrors_local_retention(roots):
    root, remote = roots
    _make_snapshot(root, "prod", "daily", "20260101T000000Z-a")
    _make_snapshot(root, "prod", "daily", "20260102T000000Z-b")
    remote_impl = offsite.LocalRemote(remote)
    offsite.sync(root, ["prod"], remote_impl, tmp_path_for_archive(tmp_path=root))

    # 模拟保留策略删掉旧快照，再同步
    import shutil
    shutil.rmtree(root / "backups/prod/daily/20260101T000000Z-a")
    result = offsite.sync(root, ["prod"], remote_impl,
                          tmp_path_for_archive(tmp_path=root))
    assert result["pruned"] == ["prod/daily/20260101T000000Z-a.tar.gz"]
    assert not (remote / "prod/daily/20260101T000000Z-a.tar.gz").exists()
    sums = (remote / offsite.SUMS_NAME).read_text(encoding="utf-8")
    assert "20260101T000000Z-a" not in sums
    assert "20260102T000000Z-b" in sums


def test_prune_removes_expired_middle_snapshot(roots):
    """被保留策略删掉的中间快照也要清远端，即使还有更老的受保护快照。"""
    root, remote = roots
    for name in ("20260101T000000Z-a", "20260102T000000Z-b",
                 "20260103T000000Z-c"):
        _make_snapshot(root, "prod", "daily", name)
    remote_impl = offsite.LocalRemote(remote)
    offsite.sync(root, ["prod"], remote_impl, tmp_path_for_archive(tmp_path=root))

    import shutil
    shutil.rmtree(root / "backups/prod/daily/20260102T000000Z-b")
    result = offsite.sync(root, ["prod"], remote_impl,
                          tmp_path_for_archive(tmp_path=root))
    assert result["pruned"] == ["prod/daily/20260102T000000Z-b.tar.gz"]
    assert (remote / "prod/daily/20260101T000000Z-a.tar.gz").is_file()
    assert (remote / "prod/daily/20260103T000000Z-c.tar.gz").is_file()


def test_prune_skips_when_local_kind_empty(roots):
    root, remote = roots
    _make_snapshot(root, "prod", "daily", "20260101T000000Z-a")
    _make_snapshot(root, "prod", "pre_change", "20260101T000000Z-p")
    remote_impl = offsite.LocalRemote(remote)
    offsite.sync(root, ["prod"], remote_impl, tmp_path_for_archive(tmp_path=root))

    import shutil
    shutil.rmtree(root / "backups/prod/pre_change")
    result = offsite.sync(root, ["prod"], remote_impl,
                          tmp_path_for_archive(tmp_path=root))
    assert result["pruned"] == []
    assert (remote / "prod/pre_change/20260101T000000Z-p.tar.gz").is_file()
    assert any("pre_change" in w for w in result["warnings"])


def test_no_local_snapshots_is_refused(roots):
    root, remote = roots
    (root / "backups").mkdir(parents=True)
    with pytest.raises(offsite.OffsiteError):
        offsite.sync(root, ["prod"], offsite.LocalRemote(remote),
                     tmp_path_for_archive(tmp_path=root))


def test_dry_run_writes_nothing(roots):
    root, remote = roots
    _make_snapshot(root, "prod", "daily", "20260101T000000Z-a")
    result = offsite.sync(root, ["prod"], offsite.LocalRemote(remote),
                          tmp_path_for_archive(tmp_path=root), dry_run=True)
    assert result["planned_uploads"] == ["prod/daily/20260101T000000Z-a.tar.gz"]
    assert not list(remote.rglob("*.tar.gz"))
    assert not (remote / offsite.SUMS_NAME).exists()


def test_render_sums_sorted_and_parse_rel():
    text = offsite.render_sums([
        ("b/x/2.tar.gz", "b" * 64),
        ("a/y/1.tar.gz", "a" * 64),
    ])
    assert text.splitlines()[0].endswith("a/y/1.tar.gz")
    assert offsite.parse_rel("prod/daily/20260101T000000Z-a.tar.gz") == (
        "prod", "daily", "20260101T000000Z-a")
    assert offsite.parse_rel("prod/20260101T000000Z-a.tar.gz") is None
    assert offsite.parse_rel("prod/daily/x.zip") is None
