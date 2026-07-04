"""多数据库管理器

管理四库分离架构下的四个独立 SQLite 数据库：
- main_db: 主业务库（高频在线，核心）
- archive_db: 业务归档冷库（过期数据）
- attach_db: 附件索引库（仅下载使用）
- log_db: 审计日志库（纯追加写入）

所有冷库、日志库禁止和主库共用数据库连接，全部单独打开、用完关闭。
"""
import os
import sqlite3
from typing import Optional
from utils.error_handler import logger
from db.database import Database


class MultiDatabaseManager:
    """多数据库管理器

    统一管理四个独立 SQLite 数据库的连接、初始化、WAL 配置。
    每个数据库独立连接，物理隔离。
    """

    _instance: Optional['MultiDatabaseManager'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        # 项目根目录
        self._root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 主库
        self.main_db: Optional[Database] = None
        # 归档冷库
        self.archive_db: Optional[Database] = None
        # 附件索引库
        self.attach_db: Optional[Database] = None
        # 审计日志库
        self.log_db: Optional[Database] = None

    def _resolve_path(self, relative_path: str) -> str:
        """将相对路径解析为绝对路径"""
        return os.path.join(self._root_dir, relative_path)

    def get_main_db(self) -> Database:
        """获取主业务库连接"""
        if self.main_db is None:
            self.main_db = Database(
                db_path=self._resolve_path("db/main.db"),
                wal_dir=self._resolve_path("db_wal/main")
            )
        return self.main_db

    def get_archive_db(self) -> Database:
        """获取归档冷库连接"""
        if self.archive_db is None:
            self.archive_db = Database(
                db_path=self._resolve_path("db/archive_cold.db"),
                wal_dir=self._resolve_path("db_wal/archive")
            )
        return self.archive_db

    def get_attach_db(self) -> Database:
        """获取附件索引库连接"""
        if self.attach_db is None:
            self.attach_db = Database(
                db_path=self._resolve_path("db/attach_cold.db"),
                wal_dir=self._resolve_path("db_wal/attach")
            )
        return self.attach_db

    def get_log_db(self) -> Database:
        """获取审计日志库连接"""
        if self.log_db is None:
            self.log_db = Database(
                db_path=self._resolve_path("db/operation_log.db"),
                wal_dir=self._resolve_path("db_wal/logdb")
            )
            # 日志库特殊优化：只有 INSERT，调低同步等级
            self.log_db.configure_synchronous("OFF")
        return self.log_db

    def init_all_databases(self):
        """初始化所有数据库表结构"""
        logger.info("开始初始化所有数据库...")

        # 1. 主库初始化（16张业务表）
        try:
            main_db = self.get_main_db()
            main_db.init_tables()
            logger.info("主库 (main.db) 初始化完成")
        except Exception as e:
            logger.error(f"主库初始化失败: {str(e)}", exception=e)
            raise

        # 2. 归档冷库初始化（与主库相同的表结构）
        try:
            archive_db = self.get_archive_db()
            self._init_archive_tables(archive_db)
            logger.info("归档冷库 (archive_cold.db) 初始化完成")
        except Exception as e:
            logger.warning(f"归档冷库初始化失败（非致命）: {str(e)}")

        # 3. 附件索引库初始化
        try:
            attach_db = self.get_attach_db()
            self._init_attach_tables(attach_db)
            logger.info("附件索引库 (attach_cold.db) 初始化完成")
        except Exception as e:
            logger.warning(f"附件索引库初始化失败（非致命）: {str(e)}")

        # 4. 审计日志库初始化
        try:
            log_db = self.get_log_db()
            self._init_log_tables(log_db)
            logger.info("审计日志库 (operation_log.db) 初始化完成")
        except Exception as e:
            logger.warning(f"审计日志库初始化失败（非致命）: {str(e)}")

        logger.info("所有数据库初始化完成")

    def _init_archive_tables(self, db: Database):
        """初始化归档冷库表结构（与主库核心表结构一致）"""
        cursor = db.connection.cursor()

        # 归档试剂瓶表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS archived_reagent_bottle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bottle_number TEXT NOT NULL,
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
                expiry_date TEXT,
                storage_location TEXT,
                archived_date TEXT DEFAULT (datetime('now')),
                archive_reason TEXT DEFAULT 'expired',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 归档领用记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS archived_borrow_record (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_number TEXT NOT NULL,
                bottle_number TEXT NOT NULL,
                reagent_name TEXT,
                user TEXT NOT NULL,
                cas_number TEXT,
                borrow_time TEXT,
                is_controlled INTEGER DEFAULT 0,
                borrow_type TEXT,
                archived_date TEXT DEFAULT (datetime('now')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 归档归还记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS archived_return_record (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                return_number TEXT NOT NULL,
                bottle_number TEXT NOT NULL,
                return_user TEXT NOT NULL,
                return_time TEXT,
                remaining_quantity REAL,
                archived_date TEXT DEFAULT (datetime('now')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.connection.commit()

    def _init_attach_tables(self, db: Database):
        """初始化附件索引库表结构"""
        cursor = db.connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attachment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                original_name TEXT,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                file_type TEXT,
                related_table TEXT,
                related_id INTEGER,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attachment_related ON attachment(related_table, related_id)")

        db.connection.commit()

    def _init_log_tables(self, db: Database):
        """初始化审计日志库表结构"""
        cursor = db.connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS operation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_type TEXT NOT NULL,
                user_name TEXT,
                action TEXT NOT NULL,
                target_table TEXT,
                target_id INTEGER,
                detail TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_log_type ON operation_log(log_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_log_user ON operation_log(user_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_log_time ON operation_log(created_at)")

        db.connection.commit()

    def close_all(self):
        """关闭所有数据库连接"""
        for db_name, db_instance in [
            ("主库", self.main_db),
            ("归档冷库", self.archive_db),
            ("附件索引库", self.attach_db),
            ("审计日志库", self.log_db),
        ]:
            if db_instance:
                try:
                    db_instance.close()
                    logger.info(f"{db_name} 连接已关闭")
                except Exception as e:
                    logger.warning(f"关闭{db_name}连接失败: {str(e)}")

    def vacuum_cold_dbs(self):
        """定期整理冷库碎片（归档库、附件库、日志库）"""
        for db_name, db_instance in [
            ("归档冷库", self.archive_db),
            ("附件索引库", self.attach_db),
            ("审计日志库", self.log_db),
        ]:
            if db_instance:
                try:
                    db_instance.vacuum()
                    logger.info(f"{db_name} VACUUM 完成")
                except Exception as e:
                    logger.warning(f"{db_name} VACUUM 失败: {str(e)}")


# 全局多数据库管理器实例
db_manager = MultiDatabaseManager()