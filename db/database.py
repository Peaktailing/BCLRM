"""SQLite 数据库连接和初始化模块

该模块提供 SQLite 数据库的连接管理和表结构初始化。
"""
import sqlite3
import os
from typing import Optional
from pathlib import Path
from utils.error_handler import logger


class Database:
    """SQLite 数据库管理类

    提供:
    - 数据库连接管理
    - 表结构初始化
    - 基础 CRUD 操作封装
    """

    _instance: Optional['Database'] = None
    _connection: Optional[sqlite3.Connection] = None

    def __new__(cls, db_path: str = None):
        """单例模式，确保全局只有一个数据库连接"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = None):
        """初始化数据库连接

        Args:
            db_path: 数据库文件路径，默认为 'db/reagent.db'
        """
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'reagent.db')

        self.db_path = db_path
        self._ensure_db_directory()

    def _ensure_db_directory(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"创建数据库目录: {db_dir}")

    @property
    def connection(self) -> sqlite3.Connection:
        """获取数据库连接（懒加载）"""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._enable_foreign_keys()
            logger.info(f"数据库连接已建立: {self.db_path}")
        return self._connection

    def _enable_foreign_keys(self):
        """启用外键约束"""
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
        except Exception as e:
            logger.error(f"启用外键约束失败: {str(e)}")

    def close(self):
        """关闭数据库连接"""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("数据库连接已关闭")

    def init_tables(self):
        """初始化所有数据表

        根据试剂管理系统的需求创建所有必要的表结构。
        """
        cursor = self.connection.cursor()

        try:
            # 1. 人员信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS person (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    role TEXT,
                    department TEXT,
                    phone TEXT,
                    student_or_work_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 2. 存储位置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS storage_location (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 3. 存储要求表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS storage_requirement (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 4. 试剂类型表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reagent_type (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 5. 供应商表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS supplier (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    contact TEXT,
                    phone TEXT,
                    address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 6. 生产商表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS manufacturer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT,
                    brand_name TEXT NOT NULL UNIQUE,
                    website TEXT,
                    attachment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 7. 管控化学品名录
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS controlled_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chemical_name TEXT NOT NULL,
                    alias TEXT,
                    cas_number TEXT,
                    dangerous_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chemical_name, cas_number)
                )
            """)

            # 8. 化学品信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chemical_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    display_name TEXT,
                    formula TEXT,
                    cas_number TEXT,
                    msds TEXT,
                    reagent_type TEXT,
                    storage_requirement TEXT,
                    controlled_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (reagent_type) REFERENCES reagent_type(name),
                    FOREIGN KEY (storage_requirement) REFERENCES storage_requirement(name)
                )
            """)

            # 9. 试剂瓶信息表（核心主表）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reagent_bottle (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bottle_number TEXT NOT NULL UNIQUE,
                    barcode TEXT,
                    reagent_name TEXT,
                    cas_number TEXT,
                    remaining_quantity REAL,
                    specification REAL,
                    purity TEXT,
                    reagent_type TEXT,
                    is_controlled INTEGER DEFAULT 0,
                    storage_requirement TEXT,
                    unit_price REAL,
                    supplier TEXT,
                    production_date TEXT,
                    inbound_date TEXT,
                    unseal_date TEXT,
                    last_borrow_time TEXT,
                    last_return_time TEXT,
                    last_return_record_no INTEGER,
                    storage_location TEXT,
                    borrowable_flag TEXT DEFAULT '可借',
                    borrowable_check INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (supplier) REFERENCES supplier(name),
                    FOREIGN KEY (storage_location) REFERENCES storage_location(name)
                )
            """)

            # 10. 领用记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS borrow_record (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_number TEXT NOT NULL UNIQUE,
                    bottle_number TEXT NOT NULL,
                    reagent_name TEXT,
                    user TEXT NOT NULL,
                    cas_number TEXT,
                    production_date TEXT,
                    is_controlled INTEGER DEFAULT 0,
                    borrow_time TEXT,
                    approver TEXT,
                    approval_file TEXT,
                    approved INTEGER,
                    is_violation INTEGER DEFAULT 0,
                    linked_return_record_number TEXT,
                    last_update_time TEXT,
                    modifier TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bottle_number) REFERENCES reagent_bottle(bottle_number),
                    FOREIGN KEY (user) REFERENCES person(name)
                )
            """)

            # 11. 归还记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS return_record (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    return_number TEXT NOT NULL UNIQUE,
                    bottle_number TEXT NOT NULL,
                    return_user TEXT NOT NULL,
                    return_time TEXT,
                    remaining_quantity REAL,
                    linked_borrow_record_number TEXT,
                    last_update_time TEXT,
                    modifier TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bottle_number) REFERENCES reagent_bottle(bottle_number),
                    FOREIGN KEY (return_user) REFERENCES person(name)
                )
            """)

            # 12. 耗材信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS consumable (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    consumable_number TEXT NOT NULL UNIQUE,
                    consumable_name TEXT NOT NULL,
                    stock_quantity INTEGER DEFAULT 0,
                    unit_price REAL,
                    supplier TEXT,
                    last_update_time TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (supplier) REFERENCES supplier(name)
                )
            """)

            # 创建索引以提高查询性能
            # 试剂瓶表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_number ON reagent_bottle(bottle_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_reagent_name ON reagent_bottle(reagent_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_cas ON reagent_bottle(cas_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_borrowable ON reagent_bottle(borrowable_flag)")

            # 领用记录表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_borrow_record_number ON borrow_record(record_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_borrow_bottle ON borrow_record(bottle_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_borrow_user ON borrow_record(user)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_borrow_time ON borrow_record(borrow_time)")

            # 归还记录表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_return_number ON return_record(return_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_return_bottle ON return_record(bottle_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_return_user ON return_record(return_user)")

            # 管控化学品表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_controlled_name ON controlled_list(chemical_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_controlled_cas ON controlled_list(cas_number)")

            # 化学品信息表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chemical_name ON chemical_info(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chemical_cas ON chemical_info(cas_number)")

            self.connection.commit()
            logger.info("数据库表初始化完成")

        except Exception as e:
            self.connection.rollback()
            logger.error(f"数据库表初始化失败: {str(e)}", exception=e)
            raise

    def execute_query(self, query: str, params: tuple = None) -> list:
        """执行查询语句

        Args:
            query: SQL 查询语句
            params: 参数元组

        Returns:
            查询结果列表
        """
        try:
            cursor = self.connection.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"查询执行失败: {str(e)}\nSQL: {query}\n参数: {params}", exception=e)
            raise

    def execute_update(self, query: str, params: tuple = None) -> int:
        """执行更新语句

        Args:
            query: SQL 更新语句
            params: 参数元组

        Returns:
            受影响的行数
        """
        try:
            cursor = self.connection.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.connection.commit()
            return cursor.rowcount
        except Exception as e:
            self.connection.rollback()
            logger.error(f"更新执行失败: {str(e)}\nSQL: {query}\n参数: {params}", exception=e)
            raise

    def execute_insert(self, query: str, params: tuple = None) -> int:
        """执行插入语句

        Args:
            query: SQL 插入语句
            params: 参数元组

        Returns:
            插入记录的 ID
        """
        try:
            cursor = self.connection.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.connection.commit()
            return cursor.lastrowid
        except Exception as e:
            self.connection.rollback()
            logger.error(f"插入执行失败: {str(e)}\nSQL: {query}\n参数: {params}", exception=e)
            raise

    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在

        Args:
            table_name: 表名

        Returns:
            表是否存在
        """
        query = """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """
        result = self.execute_query(query, (table_name,))
        return len(result) > 0


# 全局数据库实例
db = Database()