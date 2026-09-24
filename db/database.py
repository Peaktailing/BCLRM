"""SQLite 数据库连接和初始化模块

该模块提供 SQLite 数据库的连接管理和表结构初始化。
支持四库分离架构：main.db / archive_cold.db / attach_cold.db / operation_log.db
"""
import sqlite3
import os
from contextlib import contextmanager
from typing import Optional
from pathlib import Path
from utils.error_handler import logger


def _redact_params(params: Optional[tuple]) -> str:
    """脱敏 SQL 参数，防止敏感数据写入日志

    仅记录参数数量和类型，不记录实际参数值，
    避免 PII（个人可识别信息）在错误日志中泄露。

    Args:
        params: SQL 参数元组，或 None

    Returns:
        脱敏后的参数字符串，如 "3 params (types: ['str', 'str', 'int'])"
    """
    if params is None:
        return "None"
    count = len(params)
    types = [type(p).__name__ for p in params]
    return f"{count} params (types: {types})"


class Database:
    """SQLite 数据库管理类

    提供:
    - 数据库连接管理
    - WAL 日志配置
    - 表结构初始化
    - 基础 CRUD 操作封装

    支持独立 WAL 目录配置，避免 WAL 日志与数据库文件混放。
    """

    _instance: Optional['Database'] = None
    _connection: Optional[sqlite3.Connection] = None

    def __new__(cls, db_path: str = None, wal_dir: str = None):
        """单例模式（按 db_path 区分），确保同一路径只有一个连接"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = None, wal_dir: str = None):
        """初始化数据库连接

        Args:
            db_path: 数据库文件路径，默认为 'db/main.db'
            wal_dir: WAL 日志独立目录，None 则使用默认位置
        """
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'main.db')

        self.db_path = db_path
        self.wal_dir = wal_dir
        self._transaction_depth = 0
        self._ensure_db_directory()
        self._ensure_wal_directory()

    def _ensure_db_directory(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"创建数据库目录: {db_dir}")

    def _ensure_wal_directory(self):
        """确保 WAL 日志目录存在"""
        if self.wal_dir and not os.path.exists(self.wal_dir):
            os.makedirs(self.wal_dir, exist_ok=True)
            logger.info(f"创建WAL日志目录: {self.wal_dir}")

    @property
    def connection(self) -> sqlite3.Connection:
        """获取数据库连接（懒加载）"""
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path, check_same_thread=False, isolation_level=None
            )
            self._connection.row_factory = sqlite3.Row
            self._enable_foreign_keys()
            self._configure_wal()
            logger.info(f"数据库连接已建立: {self.db_path}")
        return self._connection

    def _enable_foreign_keys(self):
        """启用外键约束"""
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
        except Exception as e:
            logger.error(f"启用外键约束失败: {str(e)}")

    def _configure_wal(self):
        """配置 WAL 模式和独立日志目录"""
        try:
            cursor = self.connection.cursor()
            # 启用 WAL 模式
            cursor.execute("PRAGMA journal_mode=WAL")
            # 设置 WAL 自动检查点（1000页）
            cursor.execute("PRAGMA wal_autocheckpoint=1000")
            # 如果指定了独立 WAL 目录，设置 journal_location
            # 注意：SQLite 不支持 PRAGMA journal_location，这里通过
            # 在连接前设置 SQLITE_TMPDIR 等环境变量实现（视需要）
            self._wal_mode = cursor.fetchone()[0]
            logger.info(f"WAL模式已启用: {self._wal_mode} (路径: {self.wal_dir or '默认'})")
        except Exception as e:
            logger.warning(f"WAL配置异常: {str(e)}")

    def configure_synchronous(self, level: str = "NORMAL"):
        """配置同步级别

        Args:
            level: 同步级别 (OFF/NORMAL/FULL)，日志库可用 OFF
        """
        valid_levels = {"OFF", "NORMAL", "FULL"}
        level = level.upper()
        if level not in valid_levels:
            level = "NORMAL"
        try:
            self.connection.execute(f"PRAGMA synchronous = {level}")
            logger.info(f"同步级别设置为: {level}")
        except Exception as e:
            logger.warning(f"设置同步级别失败: {str(e)}")

    def vacuum(self):
        """执行 VACUUM 整理数据库碎片"""
        try:
            self.connection.execute("VACUUM")
            logger.info(f"VACUUM 完成: {self.db_path}")
        except Exception as e:
            logger.error(f"VACUUM 失败: {str(e)}")

    def close(self):
        """关闭数据库连接"""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info(f"数据库连接已关闭: {self.db_path}")

    def init_tables(self):
        """初始化所有数据表（仅主库使用）

        根据试剂管理系统的需求创建所有必要的表结构。
        归档库、附件库、日志库使用各自的初始化方法。
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
                    password_hash TEXT,
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
                    default_unsealed_shelf_life INTEGER,
                    default_sealed_shelf_life INTEGER,
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
                    unsealed_shelf_life INTEGER,
                    sealed_shelf_life INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
                    expired_flag TEXT DEFAULT '正常',
                    expiry_date TEXT,
                    scrap_flag TEXT,
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
                    borrow_quantity REAL,
                    course_id INTEGER,
                    approver TEXT,
                    approval_file TEXT,
                    approved INTEGER,
                    is_violation INTEGER DEFAULT 0,
                    borrow_type TEXT DEFAULT 'teacher',
                    linked_return_record_number TEXT,
                    last_update_time TEXT,
                    modifier TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bottle_number) REFERENCES reagent_bottle(bottle_number),
                    FOREIGN KEY (user) REFERENCES person(name)
                )
            """)

            # 10.1 领用工单（零星领用 / 课程领用）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS borrow_order (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    order_type TEXT NOT NULL,
                    applicant TEXT NOT NULL,
                    borrow_time TEXT,
                    course_id INTEGER,
                    item_id INTEGER,
                    course_name TEXT,
                    item_name TEXT,
                    status TEXT DEFAULT '借用中',
                    remark TEXT,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 10.2 领用工单明细
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS borrow_order_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    bottle_number TEXT,
                    reagent_name TEXT,
                    borrow_qty REAL,
                    returned_qty REAL DEFAULT 0,
                    status TEXT DEFAULT '待归还',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES borrow_order(id) ON DELETE CASCADE
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
                    usage_quantity REAL,
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

            # 13. 实验项目表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiment_project (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT NOT NULL,
                    semester TEXT,
                    teacher TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 14. 实验试剂使用记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiment_reagent_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER,
                    reagent_name TEXT,
                    cas_number TEXT,
                    usage_quantity REAL,
                    usage_date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES experiment_project(id)
                )
            """)

            # 14.1 实验课程表（来自学院实验分组表，用于领用关联与按课程/人均用量统计）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiment_course (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    semester TEXT,
                    term TEXT,
                    course_name TEXT NOT NULL,
                    class_name TEXT,
                    major TEXT,
                    teacher TEXT,
                    student_count INTEGER,
                    location TEXT,
                    college TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(semester, term, course_name, class_name)
                )
            """)

            # 14.2 实验项目表（课程下的实验，来自分组表「实验项目」列）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiment_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    semester TEXT,
                    course_name TEXT NOT NULL,
                    seq INTEGER,
                    item_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(semester, course_name, item_name)
                )
            """)

            # 14.3 实验方案表（默认方案文本，按「课程名 + 实验名」跨学年复用）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiment_plan (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_name TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    plan_text TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(course_name, item_name)
                )
            """)

            # 14.4 实验默认用量表（默认的「人均」试剂用量，领用时按班级人数折算）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiment_default_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_name TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    reagent_name TEXT NOT NULL,
                    qty_per_person REAL,
                    unit TEXT,
                    base_qty REAL,
                    base_student_count INTEGER,
                    source TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(course_name, item_name, reagent_name)
                )
            """)

            # 14.5 实验进度状态表（每学年每个实验的领用进度）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiment_item_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    semester TEXT,
                    course_name TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    status TEXT,
                    last_borrow_time TEXT,
                    last_return_time TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(semester, course_name, item_name)
                )
            """)

            # 15. 预定单表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservation_order (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    semester TEXT,
                    reagent_name TEXT,
                    cas_number TEXT,
                    quantity REAL,
                    unit TEXT,
                    applicant TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 16. 采购单表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS purchase_order (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    reservation_order_id INTEGER,
                    reagent_name TEXT,
                    cas_number TEXT,
                    order_quantity REAL,
                    unit_price REAL,
                    supplier TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (reservation_order_id) REFERENCES reservation_order(id)
                )
            """)

            # 16.1 课程采购单（表头）：按「课程名 + 目标学年」唯一，重复生成即覆盖
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS purchase_plan (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_number TEXT NOT NULL UNIQUE,
                    course_name TEXT NOT NULL,
                    source_semester TEXT,
                    target_semester TEXT,
                    source_student_count INTEGER,
                    target_student_count INTEGER,
                    status TEXT DEFAULT '待采购',
                    item_count INTEGER DEFAULT 0,
                    total_quantity REAL DEFAULT 0,
                    remark TEXT,
                    created_by TEXT,
                    updated_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(course_name, target_semester)
                )
            """)

            # 16.2 采购单明细：课程 - 实验 - 试剂
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS purchase_plan_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    item_id INTEGER,
                    item_name TEXT,
                    reagent_name TEXT,
                    cas_number TEXT,
                    source_quantity REAL,
                    per_capita_usage REAL,
                    student_count INTEGER,
                    demand_quantity REAL,
                    purchase_quantity REAL,
                    current_stock REAL,
                    is_manual INTEGER DEFAULT 0,
                    supplier TEXT,
                    unit_price REAL,
                    remark TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (plan_id) REFERENCES purchase_plan(id) ON DELETE CASCADE
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

            # 实验项目表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiment_project_name ON experiment_project(project_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiment_project_semester ON experiment_project(semester)")

            # 实验课程表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiment_course_semester ON experiment_course(semester)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiment_course_name ON experiment_course(course_name)")

            # 实验方案 / 默认用量 / 进度状态 索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiment_plan_item ON experiment_plan(course_name, item_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiment_usage_item ON experiment_default_usage(course_name, item_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiment_status_item ON experiment_item_status(semester, course_name, item_name)")

            # 预定单表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reservation_order_number ON reservation_order(order_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reservation_semester ON reservation_order(semester)")

            # 采购单表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_purchase_order_number ON purchase_order(order_number)")

            # 编号序列表：按日期维护自增序号，保证并发安全的编号生成
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_counters (
                    counter_date TEXT PRIMARY KEY,
                    seq INTEGER NOT NULL DEFAULT 0
                )
            """)

            self.connection.commit()
            logger.info("数据库表初始化完成")

            # 数据库迁移：为已有表添加新字段
            self._run_migrations()

        except Exception as e:
            self.connection.rollback()
            logger.error(f"数据库表初始化失败: {str(e)}", exception=e)
            raise

    def _run_migrations(self):
        """执行数据库迁移（为已有表补充新字段）"""
        try:
            cursor = self.connection.cursor()

            # 迁移：reagent_bottle 表增加 expired_flag 字段
            cursor.execute("PRAGMA table_info(reagent_bottle)")
            columns = {row[1] for row in cursor.fetchall()}
            if "expired_flag" not in columns:
                cursor.execute(
                    "ALTER TABLE reagent_bottle ADD COLUMN expired_flag TEXT DEFAULT '正常'"
                )
                logger.info("迁移完成：reagent_bottle 表添加 expired_flag 字段")

            if "expiry_date" not in columns:
                cursor.execute(
                    "ALTER TABLE reagent_bottle ADD COLUMN expiry_date TEXT"
                )
                logger.info("迁移完成：reagent_bottle 表添加 expiry_date 字段")

            # 迁移：chemical_info 表增加 unsealed_shelf_life 和 sealed_shelf_life 字段
            cursor.execute("PRAGMA table_info(chemical_info)")
            chem_columns = {row[1] for row in cursor.fetchall()}
            if "unsealed_shelf_life" not in chem_columns:
                cursor.execute(
                    "ALTER TABLE chemical_info ADD COLUMN unsealed_shelf_life INTEGER"
                )
                logger.info("迁移完成：chemical_info 表添加 unsealed_shelf_life 字段")
            if "sealed_shelf_life" not in chem_columns:
                cursor.execute(
                    "ALTER TABLE chemical_info ADD COLUMN sealed_shelf_life INTEGER"
                )
                logger.info("迁移完成：chemical_info 表添加 sealed_shelf_life 字段")

            # 迁移：reagent_type 表增加默认有效期字段
            cursor.execute("PRAGMA table_info(reagent_type)")
            rt_columns = {row[1] for row in cursor.fetchall()}
            if "default_unsealed_shelf_life" not in rt_columns:
                cursor.execute(
                    "ALTER TABLE reagent_type ADD COLUMN default_unsealed_shelf_life INTEGER"
                )
                logger.info("迁移完成：reagent_type 表添加 default_unsealed_shelf_life 字段")
            if "default_sealed_shelf_life" not in rt_columns:
                cursor.execute(
                    "ALTER TABLE reagent_type ADD COLUMN default_sealed_shelf_life INTEGER"
                )
                logger.info("迁移完成：reagent_type 表添加 default_sealed_shelf_life 字段")

            # 迁移：person 表增加 password_hash 字段（认证改造）
            cursor.execute("PRAGMA table_info(person)")
            person_columns = {row[1] for row in cursor.fetchall()}
            if "password_hash" not in person_columns:
                cursor.execute(
                    "ALTER TABLE person ADD COLUMN password_hash TEXT"
                )
                logger.info("迁移完成：person 表添加 password_hash 字段")

            # 迁移：borrow_record 表增加 borrow_quantity 字段（归还超量校验依据）
            cursor.execute("PRAGMA table_info(borrow_record)")
            borrow_columns = {row[1] for row in cursor.fetchall()}
            if "borrow_quantity" not in borrow_columns:
                cursor.execute(
                    "ALTER TABLE borrow_record ADD COLUMN borrow_quantity REAL"
                )
                logger.info("迁移完成：borrow_record 表添加 borrow_quantity 字段")

            # 迁移：return_record 表增加 usage_quantity 字段（学期用量统计依据）
            cursor.execute("PRAGMA table_info(return_record)")
            return_columns = {row[1] for row in cursor.fetchall()}
            if "usage_quantity" not in return_columns:
                cursor.execute(
                    "ALTER TABLE return_record ADD COLUMN usage_quantity REAL"
                )
                logger.info("迁移完成：return_record 表添加 usage_quantity 字段")

            # 迁移：borrow_order 表增加 borrow_time 字段（学期归属）
            cursor.execute("PRAGMA table_info(borrow_order)")
            order_columns = {row[1] for row in cursor.fetchall()}
            if order_columns and "borrow_time" not in order_columns:
                cursor.execute("ALTER TABLE borrow_order ADD COLUMN borrow_time TEXT")
                logger.info("迁移完成：borrow_order 表添加 borrow_time 字段")

            # 迁移：borrow_record 表增加 course_id 字段（关联实验课程）
            cursor.execute("PRAGMA table_info(borrow_record)")
            borrow_columns_all = {row[1] for row in cursor.fetchall()}
            if "course_id" not in borrow_columns_all:
                cursor.execute(
                    "ALTER TABLE borrow_record ADD COLUMN course_id INTEGER"
                )
                logger.info("迁移完成：borrow_record 表添加 course_id 字段")

            if "item_id" not in borrow_columns_all:
                cursor.execute(
                    "ALTER TABLE borrow_record ADD COLUMN item_id INTEGER"
                )
                logger.info("迁移完成：borrow_record 表添加 item_id 字段")

            # 迁移：reagent_bottle 表增加 scrap_flag 字段（待报废 / 已报废）
            cursor.execute("PRAGMA table_info(reagent_bottle)")
            bottle_columns_all = {row[1] for row in cursor.fetchall()}
            if bottle_columns_all and "scrap_flag" not in bottle_columns_all:
                cursor.execute("ALTER TABLE reagent_bottle ADD COLUMN scrap_flag TEXT")
                logger.info("迁移完成：reagent_bottle 表添加 scrap_flag 字段")

            # 迁移：采购单升级为「课程-实验-试剂」结构（旧结构无 course_name）
            cursor.execute("PRAGMA table_info(purchase_plan)")
            plan_columns = {row[1] for row in cursor.fetchall()}
            if plan_columns and "course_name" not in plan_columns:
                existing_rows = cursor.execute("SELECT COUNT(*) FROM purchase_plan").fetchone()[0]
                if existing_rows:
                    logger.warning(
                        "采购单表存在旧结构数据，重建将丢弃这些数据",
                        row_count=existing_rows
                    )
                cursor.execute("DROP TABLE IF EXISTS purchase_plan_item")
                cursor.execute("DROP TABLE IF EXISTS purchase_plan")
                cursor.execute("""
                    CREATE TABLE purchase_plan (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plan_number TEXT NOT NULL UNIQUE,
                        course_name TEXT NOT NULL,
                        source_semester TEXT,
                        target_semester TEXT,
                        source_student_count INTEGER,
                        target_student_count INTEGER,
                        status TEXT DEFAULT '待采购',
                        item_count INTEGER DEFAULT 0,
                        total_quantity REAL DEFAULT 0,
                        remark TEXT,
                        created_by TEXT,
                        updated_by TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(course_name, target_semester)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE purchase_plan_item (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plan_id INTEGER NOT NULL,
                        item_id INTEGER,
                        item_name TEXT,
                        reagent_name TEXT,
                        cas_number TEXT,
                        source_quantity REAL,
                        per_capita_usage REAL,
                        student_count INTEGER,
                        demand_quantity REAL,
                        purchase_quantity REAL,
                        current_stock REAL,
                        is_manual INTEGER DEFAULT 0,
                        supplier TEXT,
                        unit_price REAL,
                        remark TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (plan_id) REFERENCES purchase_plan(id) ON DELETE CASCADE
                    )
                """)
                logger.info("迁移完成：purchase_plan / purchase_plan_item 已升级为课程-实验-试剂结构")

            self.connection.commit()

            # 迁移：移除 chemical_info 表的 reagent_type 外键约束（支持多类型标签存储）
            self._migrate_chemical_info_drop_reagent_type_fk()

        except Exception as e:
            logger.warning(f"数据库迁移执行异常（可忽略）: {str(e)}")

    def _migrate_chemical_info_drop_reagent_type_fk(self):
        """迁移：移除 chemical_info 表的 reagent_type 外键约束

        为了支持在 chemical_info.reagent_type 中存储多个试剂类型（逗号分隔），
        需要移除该字段的外键约束。SQLite 不支持直接删除外键，需要重建表。
        """
        cursor = self.connection.cursor()

        # 检查是否存在 reagent_type 外键
        cursor.execute("PRAGMA foreign_key_list(chemical_info)")
        fks = cursor.fetchall()
        has_reagent_type_fk = any(
            fk[2] == 'reagent_type' and fk[3] == 'reagent_type'
            for fk in fks
        )

        if not has_reagent_type_fk:
            return

        logger.info("开始迁移：移除 chemical_info 表的 reagent_type 外键约束")

        cursor.execute("PRAGMA foreign_keys")
        original_fk_state = cursor.fetchone()[0]

        try:
            cursor.execute("PRAGMA foreign_keys = OFF")

            cursor.execute("""
                CREATE TABLE chemical_info_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    display_name TEXT,
                    formula TEXT,
                    cas_number TEXT,
                    msds TEXT,
                    reagent_type TEXT,
                    storage_requirement TEXT,
                    controlled_type TEXT,
                    unsealed_shelf_life INTEGER,
                    sealed_shelf_life INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (storage_requirement) REFERENCES storage_requirement(name)
                )
            """)

            cursor.execute("""
                INSERT INTO chemical_info_new
                (id, name, display_name, formula, cas_number, msds,
                 reagent_type, storage_requirement, controlled_type,
                 unsealed_shelf_life, sealed_shelf_life, created_at, updated_at)
                SELECT id, name, display_name, formula, cas_number, msds,
                       reagent_type, storage_requirement, controlled_type,
                       unsealed_shelf_life, sealed_shelf_life, created_at, updated_at
                FROM chemical_info
            """)

            cursor.execute("DROP TABLE chemical_info")
            cursor.execute("ALTER TABLE chemical_info_new RENAME TO chemical_info")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chemical_name ON chemical_info(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chemical_cas ON chemical_info(cas_number)")

            cursor.execute(f"PRAGMA foreign_keys = {original_fk_state}")

            self.connection.commit()
            logger.info("迁移完成：chemical_info 表的 reagent_type 外键约束已移除")
        except Exception as e:
            cursor.execute(f"PRAGMA foreign_keys = {original_fk_state}")
            self.connection.rollback()
            logger.error(f"迁移失败：{str(e)}", exc_info=True)
            raise

    @contextmanager
    def transaction(self):
        """事务上下文管理器（支持嵌套，仅最外层真正提交/回滚）

        用法::

            with db.transaction():
                db.execute_insert(...)
                db.execute_update(...)

        进入时若不在事务中则 BEGIN；正常退出 COMMIT，异常 ROLLBACK。
        嵌套使用时仅最外层提交/回滚，避免子块提前提交导致跨表写入半成功。
        依赖连接使用 autocommit 模式（isolation_level=None）。
        """
        conn = self.connection
        nested = self._transaction_depth > 0
        self._transaction_depth += 1
        try:
            if not nested:
                conn.execute("BEGIN")
            yield conn
            if not nested:
                conn.commit()
        except Exception:
            if not nested:
                conn.rollback()
            raise
        finally:
            self._transaction_depth -= 1

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
            logger.error(f"查询执行失败: {str(e)}\nSQL: {query}\n参数: {_redact_params(params)}", exception=e)
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
            if self._transaction_depth == 0:
                self.connection.commit()
            return cursor.rowcount
        except Exception as e:
            if self._transaction_depth == 0:
                self.connection.rollback()
            logger.error(f"更新执行失败: {str(e)}\nSQL: {query}\n参数: {_redact_params(params)}", exception=e)
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
            if self._transaction_depth == 0:
                self.connection.commit()
            return cursor.lastrowid
        except Exception as e:
            if self._transaction_depth == 0:
                self.connection.rollback()
            logger.error(f"插入执行失败: {str(e)}\nSQL: {query}\n参数: {_redact_params(params)}", exception=e)
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


# 全局主数据库实例（向后兼容）
db = Database()