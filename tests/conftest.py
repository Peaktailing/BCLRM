"""pytest 会话级防泄漏夹具。

执行版 D09：测试结束后，仓库内的真实数据目录不得新增或修改任何文件。
conftest 在会话开始时记录 db/、logs/、attachments/ 的快照，结束时比对；
任何写入都让整套测试失败，避免"测试偷偷写了真实库"这种静默污染。
"""
import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_WATCHED_DIRS = ("db", "logs", "attachments")


def _snapshot() -> dict:
    state = {}
    for name in _WATCHED_DIRS:
        root = PROJECT_ROOT / name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            # WAL/SHM 属于真实运行库的瞬时文件：dev 口径下 check_pages 等门禁
            # 与生产实例都会打开仓库库文件，仅打开就会改 -wal/-shm 的 mtime。
            # 这里只盯"数据本身"（.db/.log/.tar），避免并发跑门禁时误报。
            if path.name.endswith(("-wal", "-shm")):
                continue
            if path.suffix in (".db", ".log", ".tar", ".gz"):
                stat = path.stat()
                state[str(path)] = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    return state


@pytest.fixture(scope="session", autouse=True)
def _guard_real_data_dirs():
    before = _snapshot()
    yield
    after = _snapshot()

    changed = []
    for path, signature in after.items():
        if path not in before:
            changed.append(f"新增 {path}")
        elif before[path] != signature:
            changed.append(f"修改 {path}")
    for path in before:
        if path not in after:
            changed.append(f"删除 {path}")

    if changed and os.environ.get("BCLRM_ALLOW_REAL_DATA_WRITES") != "1":
        raise AssertionError(
            "测试写入了仓库真实数据目录（应全部落在 BCLRM_DATA_DIR 临时根）：\n  "
            + "\n  ".join(changed)
        )
