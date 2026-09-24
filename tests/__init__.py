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

# 重定向全局单例（必须先于任何业务模块导入）
_dbmod._instance = None
_test_db = _dbmod.Database(_TMP.name)
_dbmod._instance = _test_db
_dbmod.db = _test_db

# 建立空表结构（幂等）
_test_db.init_tables()

# 测试库关闭外键约束：聚焦业务逻辑流转，不依赖 person 等父表的引用完整性
_test_db.connection.execute("PRAGMA foreign_keys = OFF")

# 供测试模块使用的句柄
TEST_DB = _test_db
