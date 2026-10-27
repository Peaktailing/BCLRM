"""release 工具链测试夹具。

所有夹具都在 ``tmp_path`` 下搭一个假部署根：四库用真实 ``init_all_schemas``
生成（schema 版本就是当前 release 的 1），附件、人员、配置用最小 SQL 灌入。
绝不使用仓库的 ``db/ logs/ attachments/``。
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from deploy import release_layout as layout

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
#: 让临时 release 的 payload 能跑真实 runtime_cli，又不必复制整份代码
PAYLOAD_ENTRIES = (
    "app.py", "config", "db", "services", "business", "models", "utils",
    "components", "views", "scripts", "assets", "docs", ".streamlit",
    "requirements.txt", "deploy", "capabilities", "domain",
)


def _python_env(data_root: Path) -> Dict[str, str]:
    env = dict(os.environ)
    env.update({
        "BCLRM_ENV": "dev",
        "BCLRM_DATA_DIR": str(data_root),
        "BCLRM_MOBILE_UI": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    env.pop("BCLRM_RELEASE_FILE", None)
    env.pop("BCLRM_VERSION", None)
    return env


def init_data_root(root: Path, env: str = "prod") -> Path:
    """在临时 root 下生成四库，并灌入最小业务数据。"""
    data_root = layout.data_dir(root, env)
    code = "from db.database import init_all_schemas; init_all_schemas()"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=str(PROJECT_ROOT),
        env=_python_env(data_root), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    main_db = data_root / "db" / "main.db"
    conn = sqlite3.connect(str(main_db))
    try:
        conn.execute(
            "INSERT INTO person(name, role) VALUES ('admin', 'super_admin')"
        )
        conn.execute(
            "INSERT INTO person(name, role) VALUES ('teacher', 'teacher')"
        )
        conn.execute(
            "INSERT INTO system_config(config_key, config_value) "
            "VALUES ('mobile.base_url', 'http://127.0.0.1:8501/m')"
        )
        conn.commit()
    finally:
        conn.close()

    add_attachment(data_root)
    return data_root


def add_attachment(data_root: Path, stored_name: str = "abc123_msds.pdf",
                   content: bytes = b"msds-demo") -> Path:
    category_dir = data_root / "attachments" / "msds"
    category_dir.mkdir(parents=True, exist_ok=True)
    path = category_dir / stored_name
    path.write_bytes(content)
    conn = sqlite3.connect(str(data_root / "db" / "attach_cold.db"))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO attachment_index(stored_name, original_name, "
            "category, ref_type, ref_id, size_bytes) VALUES (?, ?, 'msds', "
            "'chemical', 'c1', ?)",
            (stored_name, stored_name, len(content)),
        )
        conn.commit()
    finally:
        conn.close()
    return path


def git_sha(repo: Path = PROJECT_ROOT) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def make_release(
    root: Path,
    version: str,
    *,
    repo: Path = PROJECT_ROOT,
    sha: Optional[str] = None,
    schema: Optional[Dict[str, int]] = None,
    register: bool = True,
) -> Path:
    """构造一个可运行 runtime_cli 的临时 release（payload 为符号链接）。"""
    version = layout.normalize_version(version)
    release = layout.release_dir(root, version)
    payload = release / "payload"
    if not payload.exists():
        payload.mkdir(parents=True)
        for entry in PAYLOAD_ENTRIES:
            source = repo / entry
            if source.exists():
                os.symlink(source, payload / entry)
    artifact = layout.payload_sha256(payload)
    doc = {
        "version": version,
        "git_sha": sha or git_sha(repo),
        "artifact_sha256": artifact,
        "python_version": layout.REQUIRED_PYTHON,
        "requirements_lock_sha256": "b" * 64,
        "schema_versions": schema or {
            "main.db": 2, "archive_cold.db": 1,
            "attach_cold.db": 1, "operation_log.db": 1,
        },
        "built_at": layout.utc_now_iso(),
    }
    layout.write_json_atomic(release / "release.json", doc)
    if register:
        layout.record_build(root, doc, release)
    return release


def write_acceptance(root: Path, version: str, *, waived: bool = True) -> Path:
    path = layout.acceptance_file(root, version)
    layout.write_json_atomic(path, {
        "version": version,
        "approved": True,
        "approver": "非AI验收人",
        "approver_type": "human",
        "signature": "SIGN-2026-001",
        "approved_at": layout.utc_now_iso(),
        "observation_waived": waived,
    })
    return path


def write_rehearsal_report(root: Path, version: str) -> Path:
    path = Path(root) / "logs" / "rehearsals" / f"test-{version}.json"
    layout.write_json_atomic(path, {
        "ok": True,
        "version": version,
        "finished_at": layout.utc_now_iso(),
        "snapshot": "test-snapshot",
        "steps": [],
        "errors": [],
    })
    return path


def tree_state(root: Path) -> Dict[str, tuple]:
    state = {}
    for path in Path(root).rglob("*"):
        if path.is_file() or path.is_symlink():
            stat = path.lstat()
            state[str(path)] = (stat.st_mtime_ns, stat.st_size)
    return state


#: 真实部署根。测试只允许读它，绝不允许任何工具把默认 root 当成测试目录。
REAL_DEPLOY_ROOT = Path("/home/biochm/BCLRM")

#: 只盯发布工具会写的结构。线上服务正常运行时 data/、logs/、backups/ 一直在变，
#: 把它们算进来会让门禁与生产运行互斥；真正要防的是“测试把 release、部署记录、
#: 验收文件写到默认根”。
_GUARDED_ENTRIES = {
    "releases", "deployments", "acceptance", "config-backups",
    "releases-index.json", "release_train.json",
}


def _real_root_state() -> Optional[Dict[str, tuple]]:
    """记录真实部署根中发布结构的快照；根不存在时返回 None。"""
    if not REAL_DEPLOY_ROOT.exists():
        return None
    state = {}
    for path in REAL_DEPLOY_ROOT.rglob("*"):
        rel = path.relative_to(REAL_DEPLOY_ROOT)
        if rel.parts[0] not in _GUARDED_ENTRIES:
            continue
        stat = path.lstat()
        state[str(path)] = (stat.st_mode, stat.st_mtime_ns, stat.st_size)
    return state


@pytest.fixture(scope="session", autouse=True)
def _guard_real_deploy_root():
    before = _real_root_state()
    yield
    after = _real_root_state()
    assert after == before, (
        "测试写入了真实部署根 /home/biochm/BCLRM；"
        "所有 release 工具测试必须显式传 --root 指向 tmp_path"
    )



@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "bclrm"
    root.mkdir()
    return root


@pytest.fixture
def prod_root(runtime_root: Path) -> Path:
    """只有 prod 数据根的临时部署根。"""
    init_data_root(runtime_root, "prod")
    return runtime_root


@pytest.fixture
def snapshot(prod_root: Path) -> Path:
    from utils import backup as backup_mod

    result = backup_mod.create_backup(
        prod_root, "prod", "pre_change", mode="cold", service_stopped=True,
        source="test", min_free_gib=0,
    )
    return Path(result["snapshot"])
