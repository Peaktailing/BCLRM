"""测试包初始化：把**整个数据根**切到临时目录。

执行版 D09 要求：在导入任何业务模块之前设置 ``BCLRM_DATA_DIR``，让
``config.settings`` 派生的四库、附件、日志全部落在临时目录；禁止再靠逐个
monkeypatch 真实路径来兜底（那种兜底漏一处就会写真实库）。

本模块是 pytest / unittest 进入测试包时最先执行的代码，因此环境变量在这里
设置，必须先于任何 ``config`` / ``db`` / ``business`` / ``services`` 导入。
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 1) 先定环境，再导入 settings —— 顺序不能反
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="bclrm-test-"))
os.environ["BCLRM_ENV"] = "dev"
os.environ["BCLRM_DATA_DIR"] = str(_TEST_ROOT)
os.environ["BCLRM_MOBILE_UI"] = "1"
os.environ.pop("BCLRM_RELEASE_FILE", None)
os.environ.pop("BCLRM_VERSION", None)

import config.settings as _settings  # noqa: E402

# 2) 断言：派生路径必须全部位于临时根内，逃逸就整体失败
_DERIVED = {
    "main": _settings.DB_MAIN_PATH,
    "archive": _settings.DB_ARCHIVE_PATH,
    "attach": _settings.DB_ATTACH_PATH,
    "log": _settings.DB_LOG_PATH,
    "logs_dir": _settings.LOG_DIR,
    "attachments": _settings.ATTACHMENTS_DIR,
}
for _name, _path in _DERIVED.items():
    if not Path(_path).resolve().is_relative_to(_TEST_ROOT):
        raise RuntimeError(f"测试数据路径逃逸临时根 [{_name}]: {_path}")

_settings.ensure_data_dirs()

import db.database as _dbmod  # noqa: E402

# 3) 默认库路径（无参 Database()）现在由 settings 派生，直接指向临时根
_test_db = _dbmod.Database()
_dbmod.db = _test_db

_test_db.init_tables()

# 测试库关闭外键约束：聚焦业务逻辑流转，不依赖 person 等父表的引用完整性
_test_db.connection.execute("PRAGMA foreign_keys = OFF")

# 4) 退出时清理临时数据根（--keep-test-data 可保留现场）
if os.environ.get("BCLRM_KEEP_TEST_DATA") != "1":
    atexit.register(shutil.rmtree, _TEST_ROOT, True)

# 供测试模块使用的句柄
TEST_DB = _test_db
TEST_DATA_ROOT = _TEST_ROOT
