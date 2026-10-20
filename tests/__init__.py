"""测试包初始化：将全局 Database 单例重定向到隔离的临时库。

该模块会在任何业务测试模块导入之前被执行（unittest/pytest 均会先导入包），
从而保证 `import business` 时 `from db.database import db` 指向临时库，
所有测试数据写入临时库，绝不污染真实 db/main.db。
"""
import os
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import db.database as _dbmod

_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()

# 1) 建立独立的测试库实例
_test_db = _dbmod.Database(_TMP.name)

# 2) 关键：把「默认库路径」（db/main.db）也指向测试库实例。
#    BaseService 内部使用 `Database()`（无参 → 默认路径），
#    只有把默认路径的缓存项替换掉，测试才真正与真实库隔离。
_default_db_path = os.path.abspath(os.path.join(PROJECT_ROOT, "db", "main.db"))
_dbmod.Database._instances[_default_db_path] = _test_db

# 3) 重定向模块级全局实例（先于任何业务模块导入）
_dbmod.db = _test_db

# 4) 审计日志库同样重定向到临时文件，避免测试追加写入真实 db/operation_log.db
#    （operation_log_service 与 init_log_db 均在调用时才读取 settings.DB_LOG_PATH，
#    本模块先于任何业务测试模块执行，覆盖必然生效）
import config.settings as _settings

_LOG_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_LOG_TMP.close()
_settings.DB_LOG_PATH = _LOG_TMP.name

# 附件索引库同样隔离，避免测试把附件索引写入真实 db/attach_cold.db
_ATTACH_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_ATTACH_TMP.close()
_settings.DB_ATTACH_PATH = _ATTACH_TMP.name

_ARCHIVE_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_ARCHIVE_TMP.close()
_settings.DB_ARCHIVE_PATH = _ARCHIVE_TMP.name

# 5) 主库默认路径同样重定向：init_log_db 的迁移源等按 DB_MAIN_PATH 新建连接，
#    统一指向测试库，避免相对路径在非仓库根目录运行时生成杂散 db/main.db
_settings.DB_MAIN_PATH = _TMP.name

# 建立空表结构（幂等）
_test_db.init_tables()

# 测试库关闭外键约束：聚焦业务逻辑流转，不依赖 person 等父表的引用完整性
_test_db.connection.execute("PRAGMA foreign_keys = OFF")

# 供测试模块使用的句柄
TEST_DB = _test_db
