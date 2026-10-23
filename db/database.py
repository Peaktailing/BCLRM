"""SQLite 数据库连接和初始化模块

该模块提供 SQLite 数据库的连接管理和表结构初始化。
支持四库分离架构：main.db / archive_cold.db / attach_cold.db / operation_log.db
"""
import sqlite3
import os
import threading
from datetime import datetime
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
    """

    _instances: dict = {}  # 按 db_path 缓存实例，支持多数据库独立连接
    _instances_lock = threading.Lock()

    def __new__(cls, db_path: str = None):
        """单例模式（按 db_path 区分），确保同一路径只有一个连接

        修复：之前忽略 db_path 参数导致四库分离架构失效，
        现在按 db_path 分别缓存实例，每个数据库路径独立管理连接。
        """
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'main.db')
        # 规范化路径避免因相对/绝对路径差异导致重复实例
        normalized = os.path.abspath(db_path)
        with cls._instances_lock:
            if normalized not in cls._instances:
                instance = super().__new__(cls)
                instance._initialized = False
                instance._connection = None  # 每个实例独立连接实例
                instance._lock = threading.RLock()  # 可重入锁，避免同一线程重复获取时死锁
                instance._local = threading.local()  # 事务深度按线程隔离
                cls._instances[normalized] = instance
            return cls._instances[normalized]

    def __init__(self, db_path: str = None):
        """初始化数据库连接

        Args:
            db_path: 数据库文件路径，默认为 'db/main.db'
        """
        # 避免重复初始化（__init__ 在 __new__ 之后总会调用）
        if hasattr(self, '_initialized') and self._initialized:
            return

        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'main.db')

        self.db_path = os.path.abspath(db_path)
        self._initialized = True
        self._ensure_db_directory()

    @property
    def _transaction_depth(self) -> int:
        """当前线程的事务嵌套深度（线程本地，避免跨会话串事务）。"""
        return getattr(self._local, "transaction_depth", 0)

    @_transaction_depth.setter
    def _transaction_depth(self, value: int) -> None:
        self._local.transaction_depth = value

    def _ensure_db_directory(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"创建数据库目录: {db_dir}")

    @property
    def connection(self) -> sqlite3.Connection:
        """获取数据库连接（懒加载）"""
        with self._lock:
            if self._connection is None:
                # isolation_level=None：关闭 sqlite3 隐式事务，改由 transaction() 显式控制
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
        """配置 WAL 模式"""
        try:
            cursor = self.connection.cursor()
            # 启用 WAL 模式
            cursor.execute("PRAGMA journal_mode=WAL")
            self._wal_mode = cursor.fetchone()[0]
            # 设置 WAL 自动检查点（1000页）
            cursor.execute("PRAGMA wal_autocheckpoint=1000")
            # 多连接/多进程写冲突时最多等待 5 秒，避免立即抛 database is locked
            cursor.execute("PRAGMA busy_timeout=5000")
            logger.info(f"WAL模式已启用: {self._wal_mode}")
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
        with self._lock:
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
                    -- 列顺序保持原样：裸 SQL 里的 SELECT * 按位置取值，重排会
                    -- 静默错位。新列只追加在末尾。
                    --
                    -- 这一行只代表「这一瓶」，不代表「这种物质」，也不代表
                    -- 「这批货」——那两件事在 chemical_info 与 bottle_lot。
                    -- 带 ☆ 的列是共享或派生值，第二段迁移后删除，读到的是
                    -- 档案 / 批次表 / 借还汇总视图。
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bottle_number TEXT NOT NULL UNIQUE,
                    barcode TEXT,
                    reagent_name TEXT,          -- ☆ 物质：chemical_info.name
                    cas_number TEXT,            -- ☆ 物质：chemical_info.cas_number
                    remaining_quantity REAL,    -- ☆ 派生：借还流水汇总
                    specification REAL,         -- ☆ 批次：bottle_lot.specification
                    unit TEXT DEFAULT 'g',      -- ☆ 批次：bottle_lot.unit
                    purity TEXT,                -- ☆ 物质：chemical_info.purity_default
                    reagent_type TEXT,          -- ☆ 物质：chemical_info.reagent_type
                    is_controlled INTEGER DEFAULT 0,   -- ☆ 物质：controlled_list 命中
                    storage_requirement TEXT,   -- ☆ 物质：chemical_info.storage_requirement
                    unit_price REAL,            -- ☆ 批次：bottle_lot.unit_price
                    supplier TEXT,              -- ☆ 批次：bottle_lot.supplier
                    production_date TEXT,       -- ☆ 批次：bottle_lot.production_date
                    inbound_date TEXT,          -- ☆ 批次：bottle_lot.inbound_date
                    unseal_date TEXT,
                    last_borrow_time TEXT,      -- ☆ 派生：最近一张领用单
                    last_return_time TEXT,      -- ☆ 派生：最近一条归还记录
                    last_return_record_no INTEGER,     -- ☆ 派生同上
                    storage_location TEXT,      -- ☆ 位置：bottle_placement 最新一条
                    borrowable_flag TEXT DEFAULT '可借',  -- 业务状态：可借/已借出/耗尽/空瓶（与 borrowable_check 同步）
                    borrowable_check INTEGER DEFAULT 1,  -- borrowable_check: 1=可借, 0=不可借
                    expired_flag TEXT DEFAULT '正常',
                    expiry_date TEXT,           -- ☆ 批次：bottle_lot.expiry_date
                    scrap_flag TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    -- 范式化指针（追加）：物质、批次、当前位置的落表时间
                    chemical_id INTEGER,
                    lot_id INTEGER,
                    placement_at TIMESTAMP,
                    -- 写入版本（追加）：每次写入 +1，供「只能改我看到的那一版」
                    -- 的乐观锁使用（见 db/base_service.py）。不是同步水位，
                    -- 与 Lims 的 sync_version 同源不同用：本仓单机单写，
                    -- 只需要知道「有没有人动过」。
                    rev INTEGER DEFAULT 0,
                    FOREIGN KEY (supplier) REFERENCES supplier(name),
                    FOREIGN KEY (storage_location) REFERENCES storage_location(name),
                    FOREIGN KEY (chemical_id) REFERENCES chemical_info(id),
                    FOREIGN KEY (lot_id) REFERENCES bottle_lot(id)
                )
            """)

            # 9.1 管理人变更记录表（保管权流转历史）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS manager_change_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bottle_number TEXT NOT NULL,
                    reagent_name TEXT,
                    old_manager TEXT,
                    new_manager TEXT,
                    reason TEXT,
                    ref_type TEXT,
                    ref_id TEXT,
                    remark TEXT,
                    operator TEXT,
                    changed_at TEXT
                )
            """)

            # 9.2 需求单表（领用需求 → 拆分为多张调配单）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reagent_demand (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    demand_number TEXT NOT NULL UNIQUE,
                    requester TEXT NOT NULL,
                    order_type TEXT,
                    course_id INTEGER,
                    item_id INTEGER,
                    project_id INTEGER,
                    course_name TEXT,
                    item_name TEXT,
                    borrow_time TEXT,
                    status TEXT,
                    remark TEXT,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 9.3 需求单明细表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reagent_demand_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    demand_id INTEGER NOT NULL,
                    reagent_name TEXT,
                    cas_number TEXT,
                    requested_qty REAL
                )
            """)

            # 9.4 调配单表（按管理人拆分，发到对应管理员手上）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS allocation_order (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    allocation_number TEXT NOT NULL UNIQUE,
                    demand_id INTEGER,
                    manager TEXT,
                    status TEXT,
                    demand_qty REAL,
                    manager_stock_qty REAL,
                    total_stock_qty REAL,
                    year_demand_qty REAL,
                    is_stock_sufficient INTEGER,
                    handled_at TEXT,
                    remark TEXT,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 9.5 调配单明细表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS allocation_order_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    allocation_id INTEGER NOT NULL,
                    bottle_number TEXT,
                    reagent_name TEXT,
                    qty REAL,
                    status TEXT
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
                    unit TEXT DEFAULT 'g',
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
                    approval_status TEXT DEFAULT '无需审批',
                    approver TEXT,
                    approval_time TEXT,
                    approval_remark TEXT,
                    remark TEXT,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    -- 来源需求单号（追加末尾）。需求单转借出单时回填，
                    -- 用于「这张领用单是为哪张需求单发的」反查。
                    requirement_number TEXT
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
                    unit TEXT DEFAULT 'g',
                    status TEXT DEFAULT '待归还',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    -- 这张明细兑付的是哪一条需求行。一行分两瓶时这里相同，
                    -- 一行分两次发时每次一张单、各自指回同一条需求行。
                    requirement_line_id INTEGER,
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
                    unit TEXT DEFAULT 'g',
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
                    approver TEXT,
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

            # 14.6 审计日志表（记录关键操作，纯追加写入）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operator TEXT,
                    action TEXT,
                    target_type TEXT,
                    target_id TEXT,
                    detail TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                    unit TEXT DEFAULT 'g',
                    unit_price REAL,
                    supplier TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (reservation_order_id) REFERENCES reservation_order(id)
                )
            """)

            # 17. 化学品-试剂类型关联表（替代 chemical_info.reagent_type CSV 字段）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chemical_reagent_type (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chemical_id INTEGER NOT NULL,
                    type_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chemical_id) REFERENCES chemical_info(id) ON DELETE CASCADE,
                    FOREIGN KEY (type_id) REFERENCES reagent_type(id) ON DELETE CASCADE,
                    UNIQUE(chemical_id, type_id)
                )
            """)

            # 为所有含 updated_at 字段的表创建 AFTER UPDATE 触发器
            _trigger_tables = [
                "person", "storage_location", "storage_requirement",
                "reagent_type", "supplier", "manufacturer", "controlled_list",
                "chemical_info", "reagent_bottle", "borrow_record",
                "return_record", "consumable", "experiment_project",
                "borrow_order", "experiment_course",
                "reservation_order", "purchase_order",
            ]
            for _tbl in _trigger_tables:
                cursor.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS trg_{_tbl}_updated_at
                    AFTER UPDATE ON {_tbl}
                    FOR EACH ROW
                    BEGIN
                        UPDATE {_tbl} SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                    END;
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
                    approval_status TEXT DEFAULT '无需审批',
                    approver TEXT,
                    approval_time TEXT,
                    approval_remark TEXT,
                    remark TEXT,
                    created_by TEXT,
                    updated_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(course_name, target_semester)
                )
            """)
            # purchase_plan 在上面的通用触发器循环之后才建表，单独补触发器
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_purchase_plan_updated_at
                AFTER UPDATE ON purchase_plan
                FOR EACH ROW
                BEGIN
                    UPDATE purchase_plan SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END;
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
                    unit TEXT DEFAULT 'g',
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

            # ------------------------------------------------------------------
            # 18. 物料交叉点：配方 → 需求单
            #
            # 这四张表是「试剂流转」与「实验过程」两条纵线的唯一交汇处：
            # 配方只声明「要什么、多少」，不关心实验属于教学还是科研；
            # 需求单是算出来的快照，只追加不改写，历史可复盘。
            # ------------------------------------------------------------------

            # 18.1 配方（实验方案的物料侧）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recipe (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipe_key TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'draft',
                    source_kind TEXT,
                    source_code TEXT,
                    source_title TEXT,
                    owner TEXT,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 18.2 配方组分（计量规则多态落库：amount_type + 扁平参数）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recipe_component (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipe_id INTEGER NOT NULL,
                    seq INTEGER DEFAULT 0,
                    role TEXT NOT NULL,
                    substance_key TEXT NOT NULL,
                    display_name TEXT,
                    cas_number TEXT,
                    formula TEXT,
                    amount_type TEXT NOT NULL DEFAULT 'per_person',
                    amount_value REAL,
                    amount_unit TEXT,
                    ref_key TEXT,
                    concentration REAL,
                    concentration_unit TEXT,
                    coefficient REAL DEFAULT 1,
                    purity_required REAL,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (recipe_id) REFERENCES recipe(id) ON DELETE CASCADE
                )
            """)

            # 18.3 需求单头（配方 × 规模 的一次计算结果，只追加）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS requirement_sheet (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sheet_number TEXT NOT NULL UNIQUE,
                    recipe_id INTEGER,
                    recipe_key TEXT,
                    title TEXT,
                    status TEXT DEFAULT 'draft',
                    persons INTEGER DEFAULT 1,
                    batches INTEGER DEFAULT 1,
                    vessel_volume REAL,
                    vessel_unit TEXT,
                    scale_label TEXT,
                    requester TEXT,
                    source_kind TEXT,
                    source_code TEXT,
                    warnings TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    -- 学年（9/1 起算，形如 2026-2027）。需求以学年为周期，
                    -- 保底只在当前学年内累计，跨年自动翻篇。
                    -- 新列一律追加在末尾：裸 SQL 里的 SELECT * 按位置取值。
                    academic_year TEXT,
                    -- 兑付：转成的借出单号、兑付时刻与发料人。借出即兑付——
                    -- 料真的发出去了，这张单才退出保底累计（保底只认 submitted）。
                    order_number TEXT,
                    issued_at TIMESTAMP,
                    issued_by TEXT
                )
            """)

            # 18.4 需求明细（含评估时的可用量/缺口快照）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS requirement_line (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sheet_id INTEGER NOT NULL,
                    seq INTEGER DEFAULT 0,
                    substance_key TEXT,
                    display_name TEXT,
                    cas_number TEXT,
                    role TEXT,
                    quantity REAL,
                    unit TEXT,
                    basis_text TEXT,
                    explanation TEXT,
                    purity_required REAL,
                    is_controlled INTEGER DEFAULT 0,
                    available_quantity REAL,
                    gap_quantity REAL,
                    coverage_ratio REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    -- 兑付落在**行**上，不是单头。一张单可能今天只发得出 5 项，
                    -- 剩下 15 项要等料。整单置 issued 会把那 15 项静默吞掉：
                    -- 既不在保底里（状态不是 submitted），也不在任何待办上。
                    --   issued_quantity  累计已发（记回本行的 unit，可直接与
                    --                    quantity 相减得余量）
                    --   status           open / partial / issued
                    --   order_number     最后一次兑付本行的那张借出单
                    issued_quantity REAL DEFAULT 0,
                    status TEXT DEFAULT 'open',
                    order_number TEXT,
                    FOREIGN KEY (sheet_id) REFERENCES requirement_sheet(id) ON DELETE CASCADE
                )
            """)

            # 18.5 保管人路由（谁受理哪门课/哪个项目/哪个科室的申请）
            #
            # 这张表补的是 BCLRM 一直缺的那一环：课程与管理员之间没有映射。
            # 没有它，教师申领时系统只能去全院撮合，于是"该课的管理员"永远
            # 不知道自己名下缺货，第二段的横向调配也就永远不会被触发。
            #
            # 用独立表而不是给 experiment_course 加列：同一套路由规则还要
            # 覆盖科研项目、教研室，甚至"某个老师个人"，加列加不完。
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS custodian_route (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_type TEXT NOT NULL,          -- course / project / department / person
                    scope_key TEXT NOT NULL DEFAULT '',-- 课程名或「课程/班级」、项目号、科室名
                    custodian TEXT NOT NULL,           -- 受理管理员
                    priority INTEGER DEFAULT 100,      -- 数值小的先匹配
                    remark TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(scope_type, scope_key)
                )
            """)

            # 19. 系统配置（键值对）
            #
            # 为什么要一张表而不是写死在 config/settings.py：这里放的是
            # **随现场变、要由超管当场改**的开关。「借出要不要拍照」这种
            # 问题，答案取决于这个实验室的危化品管理口径，改一次不该发版。
            # 常量留在代码里只适合「改了就错」的东西（表名、路径）。
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_key TEXT NOT NULL UNIQUE,
                    config_value TEXT,
                    remark TEXT,
                    updated_by TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 新增表的 updated_at 触发器（上面通用循环建立时这几张表还不存在）
            for _tbl in ("recipe", "requirement_sheet", "custodian_route", "system_config"):
                cursor.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS trg_{_tbl}_updated_at
                    AFTER UPDATE ON {_tbl}
                    FOR EACH ROW
                    BEGIN
                        UPDATE {_tbl} SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                    END;
                """)

            # 创建索引以提高查询性能
            # 试剂瓶表索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_number ON reagent_bottle(bottle_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_reagent_name ON reagent_bottle(reagent_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_cas ON reagent_bottle(cas_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_borrowable_check ON reagent_bottle(borrowable_check)")

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

            # 审计日志索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_log_time ON operation_log(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_log_action ON operation_log(action)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_log_operator ON operation_log(operator)")

            # 配方 / 需求单索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_status ON recipe(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_source ON recipe(source_kind, source_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_component_recipe ON recipe_component(recipe_id, seq)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_component_key ON recipe_component(substance_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_requirement_sheet_recipe ON requirement_sheet(recipe_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_requirement_sheet_status ON requirement_sheet(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_requirement_line_sheet ON requirement_line(sheet_id, seq)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_requirement_line_key ON requirement_line(substance_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_custodian_route_scope ON custodian_route(scope_type, scope_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_custodian_route_custodian ON custodian_route(custodian)")

            # ── 试剂瓶的批次与位置（范式化的第一步，见 docs/表规范与范式化设计.md）──
            # bottle_lot：一次采购到货的一批瓶子共享的供应商/货号/批号/日期/
            # 单价/包装规格。原先这些是 reagent_bottle 上的列，五瓶同一箱到货
            # 就要写五遍，改一次有效期要改五行。现在写一遍，瓶子指过来。
            #
            # 与 Lims 仓的 chem_lot 对应：那边主键 id + substance_id_fk，
            # 这边 id + chemical_id（主仓的化学品档案是 chemical_info）。
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bottle_lot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chemical_id INTEGER,
                    supplier TEXT,
                    catalog_number TEXT,
                    lot_number TEXT,
                    unit_price REAL,
                    specification REAL,
                    unit TEXT DEFAULT 'g',
                    production_date TEXT,
                    inbound_date TEXT,
                    expiry_date TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chemical_id) REFERENCES chemical_info(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_lot_chemical ON bottle_lot(chemical_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_lot_number ON bottle_lot(lot_number)")

            # bottle_placement：一瓶试剂放在哪，以及以前放在哪。原先只有
            # reagent_bottle.storage_location 一个当前值，历史丢失；而教学
            # 实验室恰恰要回答「这瓶什么时候、被谁放到学生台上」。
            # 位置变更是一串事件，当前值是最新那条（v_bottle_current_place）。
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bottle_placement (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bottle_number TEXT NOT NULL,
                    storage_location TEXT,
                    moved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    moved_by TEXT,
                    note TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bottle_placement_bottle ON bottle_placement(bottle_number, moved_at)")
            # 当前位置 = 这一瓶最新的一条位置记录。用 MAX(id) 而不是
            # MAX(moved_at)：同一秒挪两次时时间戳并列，id 才是顺序。
            cursor.execute("""
                CREATE VIEW IF NOT EXISTS v_bottle_current_place AS
                SELECT p.bottle_number, p.storage_location, p.moved_at, p.moved_by, p.note
                FROM bottle_placement p
                WHERE p.id = (SELECT MAX(q.id) FROM bottle_placement q
                              WHERE q.bottle_number = p.bottle_number)
            """)

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

            # 数据清洗：历史批量导入将 NaN 写成字符串 'nan'，规范为 NULL（幂等）
            cursor.execute("UPDATE chemical_info SET msds = NULL WHERE msds = 'nan'")
            if cursor.rowcount:
                logger.info(f"迁移完成：清洗 chemical_info.msds 'nan' 污染值 {cursor.rowcount} 条")

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

            # 迁移：reagent_bottle 表增加 manager 字段（当前管理人/保管权归属）
            if bottle_columns_all and "manager" not in bottle_columns_all:
                cursor.execute("ALTER TABLE reagent_bottle ADD COLUMN manager TEXT")
                logger.info("迁移完成：reagent_bottle 表添加 manager 字段")
                # 仅在新增列时回填一次历史数据（此后启动不再覆盖人工调整过的管理人）
                cursor.execute(
                    "UPDATE reagent_bottle SET manager = ("
                    "SELECT name FROM person WHERE role = 'super_admin' ORDER BY id LIMIT 1"
                    ") WHERE manager IS NULL OR manager = ''"
                )
                if cursor.rowcount and cursor.rowcount > 0:
                    logger.info(
                        f"迁移完成：已为 {cursor.rowcount} 个无管理人的试剂瓶回填超级管理员"
                    )

            # 迁移：purchase_plan_item 表增加 bottle_number 字段（按采购单入库后回填，防重复入库）
            cursor.execute("PRAGMA table_info(purchase_plan_item)")
            plan_item_columns = {row[1] for row in cursor.fetchall()}
            if plan_item_columns and "bottle_number" not in plan_item_columns:
                cursor.execute(
                    "ALTER TABLE purchase_plan_item ADD COLUMN bottle_number TEXT"
                )
                logger.info("迁移完成：purchase_plan_item 表添加 bottle_number 字段")

            # 迁移：experiment_course 表增加 approver 字段（课程绑定的审批管理员）
            cursor.execute("PRAGMA table_info(experiment_course)")
            course_columns = {row[1] for row in cursor.fetchall()}
            if course_columns and "approver" not in course_columns:
                cursor.execute("ALTER TABLE experiment_course ADD COLUMN approver TEXT")
                logger.info("迁移完成：experiment_course 表添加 approver 字段")

            # 迁移：工单 / 采购单增加审批流字段
            for _tbl, _cols in (
                ("borrow_order", ("approval_status", "approver", "approval_time", "approval_remark")),
                ("purchase_plan", ("approval_status", "approver", "approval_time", "approval_remark")),
            ):
                cursor.execute(f"PRAGMA table_info({_tbl})")
                _existing = {row[1] for row in cursor.fetchall()}
                if not _existing:
                    continue
                if "approval_status" not in _existing:
                    cursor.execute(
                        f"ALTER TABLE {_tbl} ADD COLUMN approval_status TEXT DEFAULT '无需审批'"
                    )
                    logger.info(f"迁移完成：{_tbl} 表添加 approval_status 字段")
                for _col in _cols[1:]:
                    if _col not in _existing:
                        cursor.execute(f"ALTER TABLE {_tbl} ADD COLUMN {_col} TEXT")
                        logger.info(f"迁移完成：{_tbl} 表添加 {_col} 字段")

            # 迁移：borrow_order 增加 project_id（关联非课程类实验项目）
            cursor.execute("PRAGMA table_info(borrow_order)")
            bo_cols = {row[1] for row in cursor.fetchall()}
            if bo_cols and "project_id" not in bo_cols:
                cursor.execute("ALTER TABLE borrow_order ADD COLUMN project_id INTEGER")
                logger.info("迁移完成：borrow_order 表添加 project_id 字段")

            # 迁移：experiment_reagent_usage 台账补充课程/实验/学期维度
            cursor.execute("PRAGMA table_info(experiment_reagent_usage)")
            eru_cols = {row[1] for row in cursor.fetchall()}
            for _col in ("course_name", "item_name", "semester"):
                if eru_cols and _col not in eru_cols:
                    cursor.execute(
                        f"ALTER TABLE experiment_reagent_usage ADD COLUMN {_col} TEXT"
                    )
                    logger.info(f"迁移完成：experiment_reagent_usage 表添加 {_col} 字段")

            # 迁移：采购单升级为「课程-实验-试剂」结构（旧结构无 course_name）
            cursor.execute("PRAGMA table_info(purchase_plan)")
            plan_columns = {row[1] for row in cursor.fetchall()}
            if plan_columns and "course_name" not in plan_columns:
                existing_rows = cursor.execute("SELECT COUNT(*) FROM purchase_plan").fetchone()[0]
                if existing_rows:
                    logger.warning(
                        "采购单表存在旧结构数据，将重命名为 legacy 表保留而非删除",
                        row_count=existing_rows
                    )
                _legacy_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
                cursor.execute(
                    f"ALTER TABLE purchase_plan RENAME TO purchase_plan_legacy_{_legacy_suffix}"
                )
                cursor.execute(
                    f"ALTER TABLE purchase_plan_item RENAME TO purchase_plan_item_legacy_{_legacy_suffix}"
                )
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
                        unit TEXT DEFAULT 'g',
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
                logger.info("迁移完成：purchase_plan / purchase_plan_item  已升级为课程-实验-试剂结构")

            # 迁移：为既有表补充 unit 字段（历史数据默认 g）
            for _tbl in (
                "reagent_bottle", "borrow_record", "return_record",
                "borrow_order_item", "purchase_plan_item", "purchase_order",
            ):
                cursor.execute(f"PRAGMA table_info({_tbl})")
                _cols = {row[1] for row in cursor.fetchall()}
                if _cols and "unit" not in _cols:
                    cursor.execute(
                        f"ALTER TABLE {_tbl} ADD COLUMN unit TEXT DEFAULT 'g'"
                    )
                    logger.info(f"迁移完成：{_tbl} 表添加 unit 字段")

            # ── 迁移：化学域范式化（共享信息上移到档案 / 批次 / 位置）──
            # 判据只有一条：这一列是「随事件变化」「被多行共享」还是「一批货
            # 共享」。随事件变化 → 事件表；被多行共享 → 物质档案；一批货共享
            # → 批次表。原 reagent_bottle 三十列里，前三类各占了一部分，
            # 只有「编号、位置指针、备注、时间戳」真正属于这一瓶。
            #
            # 这一段只做加法：新列、新表、回填。旧列一个不删，写入时双写，
            # 读路径逐步切换（expand → migrate → contract）。设计依据见
            # docs/表规范与范式化设计.md。

            # 1) chemical_info 补齐物质固有属性：这些原先是每一瓶各写一份的
            cursor.execute("PRAGMA table_info(chemical_info)")
            chem_cols = {row[1] for row in cursor.fetchall()}
            for _col, _ddl in (
                ("molecular_weight", "REAL"),
                # g/mL。跨量纲换算唯一依赖的数：需求写克、库存是毫升时，
                # 没有密度只能拒绝换算，不能猜。
                ("density", "REAL"),
                ("purity_default", "REAL"),
                ("grade_default", "TEXT"),
                ("alias", "TEXT"),
                ("hazard", "TEXT"),
                ("msds_url", "TEXT"),
            ):
                if chem_cols and _col not in chem_cols:
                    cursor.execute(f"ALTER TABLE chemical_info ADD COLUMN {_col} {_ddl}")
                    logger.info(f"迁移完成：chemical_info 表添加 {_col} 字段（物质固有属性）")

            # 2) controlled_list 取两仓并集：notes 与 sync_version 来自 Lims 仓，
            #    updated_at 与唯一约束本仓原有。sync_version 本仓不读写，
            #    留着是为了合仓时 Lims 的离线增量同步不断。
            cursor.execute("PRAGMA table_info(controlled_list)")
            ctl_cols = {row[1] for row in cursor.fetchall()}
            for _col, _ddl in (("notes", "TEXT"), ("sync_version", "INTEGER DEFAULT 0")):
                if ctl_cols and _col not in ctl_cols:
                    cursor.execute(f"ALTER TABLE controlled_list ADD COLUMN {_col} {_ddl}")
                    logger.info(f"迁移完成：controlled_list 表添加 {_col} 字段（与 Lims 并集）")

            # 3) reagent_bottle 加三个指针：物质、批次、位置时间；外加写入版本
            cursor.execute("PRAGMA table_info(reagent_bottle)")
            rb_cols = {row[1] for row in cursor.fetchall()}
            for _col, _ddl in (
                ("chemical_id", "INTEGER"),
                ("lot_id", "INTEGER"),
                ("placement_at", "TIMESTAMP"),
                # 老库没有 rev：加上并留 0。此后每次写入自增（db/base_service.py
                # 的 update/update_by_field/update_where），存量行从 0 开始数。
                ("rev", "INTEGER DEFAULT 0"),
            ):
                if rb_cols and _col not in rb_cols:
                    cursor.execute(f"ALTER TABLE reagent_bottle ADD COLUMN {_col} {_ddl}")
                    logger.info(f"迁移完成：reagent_bottle 表添加 {_col} 字段（范式化指针）")

            # 4) requirement_sheet 加学年：需求以学年为周期（9/1 起算），
            #    保底只在当前学年内累计，跨年自动翻篇。回填按 created_at
            #    推——老库没有这一列，必须给历史单一个归属，否则它们永远
            #    落在「学年不明」里，既不参与统计也不参与保底。
            cursor.execute("PRAGMA table_info(requirement_sheet)")
            rs_cols = {row[1] for row in cursor.fetchall()}
            if rs_cols and "academic_year" not in rs_cols:
                cursor.execute("ALTER TABLE requirement_sheet ADD COLUMN academic_year TEXT")
                from utils.semester_utils import date_to_semester

                for _sid, _created in cursor.execute(
                        "SELECT id, created_at FROM requirement_sheet").fetchall():
                    _label = date_to_semester(_created)
                    if _label:
                        cursor.execute(
                            "UPDATE requirement_sheet SET academic_year = ? WHERE id = ?",
                            (_label, _sid),
                        )
                logger.info("迁移完成：requirement_sheet 表添加 academic_year 字段")

            # 5) requirement_sheet 加兑付三列：转借出单后回填。老单没有这三
            #    列，留 NULL——「没兑付过」本来就是 NULL 的语义，不需要回填。
            for _col, _ddl in (
                ("order_number", "TEXT"),
                ("issued_at", "TIMESTAMP"),
                ("issued_by", "TEXT"),
            ):
                if rs_cols and _col not in rs_cols:
                    cursor.execute(f"ALTER TABLE requirement_sheet ADD COLUMN {_col} {_ddl}")
                    logger.info(f"迁移完成：requirement_sheet 表添加 {_col} 字段（兑付）")

            # 6) requirement_line 加兑付三列：兑付粒度从单头下沉到明细行。
            #    老单一个都没兑过，issued_quantity 补 0、status 补 open 即可
            #    ——这两个默认值本身就是「没兑付」的正确表达，不需要别的回填。
            cursor.execute("PRAGMA table_info(requirement_line)")
            rl_cols = {row[1] for row in cursor.fetchall()}
            for _col, _ddl in (
                ("issued_quantity", "REAL DEFAULT 0"),
                ("status", "TEXT DEFAULT 'open'"),
                ("order_number", "TEXT"),
            ):
                if rl_cols and _col not in rl_cols:
                    cursor.execute(f"ALTER TABLE requirement_line ADD COLUMN {_col} {_ddl}")
                    logger.info(f"迁移完成：requirement_line 表添加 {_col} 字段（逐项兑付）")

            # 7) borrow_order_item 加来源需求行：一张借出单里两个瓶可能来自
            #    两条需求行，回头要对「这条需求行发了多少」只能靠它。
            cursor.execute("PRAGMA table_info(borrow_order_item)")
            boi_cols = {row[1] for row in cursor.fetchall()}
            if boi_cols and "requirement_line_id" not in boi_cols:
                cursor.execute(
                    "ALTER TABLE borrow_order_item ADD COLUMN requirement_line_id INTEGER"
                )
                logger.info("迁移完成：borrow_order_item 表添加 requirement_line_id 字段")

            # 8) borrow_order 加来源需求单：借出单要能反查「这张单是为哪张需求
            #    单发的」，否则兑付对账只能靠人回忆。
            cursor.execute("PRAGMA table_info(borrow_order)")
            bo_cols = {row[1] for row in cursor.fetchall()}
            if bo_cols and "requirement_number" not in bo_cols:
                cursor.execute("ALTER TABLE borrow_order ADD COLUMN requirement_number TEXT")
                logger.info("迁移完成：borrow_order 表添加 requirement_number 字段")

            if rb_cols:
                # 4) 回填物质外键：CAS 优先（唯一），名称兜底。CAS 为空不算声明，                #    与 chemical_info 的唯一索引口径一致。
                #    用 Python 配对而不是一条相关子查询的 UPDATE：SQLite 在子查询
                #    里看不到正在被更新的那张表，`reagent_bottle.cas_number` 会报
                #    no such column（0049 的 Lims 迁移踩过同一个坑）。
                _by_cas, _by_name = {}, {}
                for _cid, _cname, _ccas in cursor.execute(
                        "SELECT id, name, cas_number FROM chemical_info").fetchall():
                    if _cname:
                        _by_name.setdefault(_cname.strip(), _cid)
                    if _ccas and _ccas.strip():
                        _by_cas.setdefault(_ccas.strip(), _cid)
                _matched = 0
                for _no, _cas, _name in cursor.execute(
                        "SELECT bottle_number, cas_number, reagent_name FROM reagent_bottle "
                        "WHERE chemical_id IS NULL").fetchall():
                    _cid = _by_cas.get((_cas or "").strip()) or _by_name.get((_name or "").strip())
                    if _cid is not None:
                        cursor.execute(
                            "UPDATE reagent_bottle SET chemical_id = ? WHERE bottle_number = ?",
                            (_cid, _no))
                        _matched += 1
                if _matched:
                    logger.info(f"迁移完成：{_matched} 个试剂瓶已关联物质档案")

                # 5) 回填批次：一次到货 = 同一物质 + 同一供应商 + 同一单价 + 同一规格。
                #    没有厂家批号可依据，这四项是能拿到的最强签名。
                cursor.execute("""
                    SELECT bottle_number, chemical_id, supplier, unit_price, specification,
                           unit, production_date, inbound_date, expiry_date, created_at
                    FROM reagent_bottle WHERE lot_id IS NULL
                """)
                _lots = {}
                _filled = 0
                for (_no, _chem, _sup, _price, _spec, _unit, _prod, _in, _exp, _created) in cursor.fetchall():
                    _key = (_chem, _sup, _price, _spec)
                    _lot = _lots.get(_key)
                    if _lot is None:
                        cursor.execute("""
                            INSERT INTO bottle_lot
                                (chemical_id, supplier, unit_price, specification, unit,
                                 production_date, inbound_date, expiry_date, notes, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', COALESCE(?, CURRENT_TIMESTAMP))
                        """, (_chem, _sup, _price, _spec, _unit or "g", _prod, _in, _exp, _created))
                        _lot = cursor.lastrowid
                        _lots[_key] = _lot
                    cursor.execute("UPDATE reagent_bottle SET lot_id = ? WHERE bottle_number = ?", (_lot, _no))
                    _filled += 1
                if _filled:
                    logger.info(f"迁移完成：{_filled} 个试剂瓶已归入 {len(_lots)} 个来源批次")

                # 6) 回填位置：每瓶写一条当前位置。此后每次挪动追加一条，
                #    当前值取最新那条，历史不再丢。
                cursor.execute("""
                    INSERT INTO bottle_placement (bottle_number, storage_location, moved_at, moved_by, note)
                    SELECT b.bottle_number, b.storage_location,
                           COALESCE(b.created_at, CURRENT_TIMESTAMP), '', '初始位置（迁移回填）'
                    FROM reagent_bottle b
                    WHERE NOT EXISTS (SELECT 1 FROM bottle_placement p WHERE p.bottle_number = b.bottle_number)
                """)
                if cursor.rowcount and cursor.rowcount > 0:
                    logger.info(f"迁移完成：{cursor.rowcount} 个试剂瓶的当前位置已写入 bottle_placement")

            self.connection.commit()

            # 迁移：移除 chemical_info 表的 reagent_type 外键约束（支持多类型标签存储）
            self._migrate_chemical_info_drop_reagent_type_fk()

            # 迁移：将 chemical_info.reagent_type 的 CSV 数据迁移到 chemical_reagent_type 关联表
            cursor.execute("PRAGMA table_info(chemical_reagent_type)")
            has_junction_table = len(cursor.fetchall()) > 0
            if has_junction_table:
                cursor.execute("SELECT COUNT(*) FROM chemical_reagent_type")
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "SELECT id, reagent_type FROM chemical_info WHERE reagent_type IS NOT NULL AND reagent_type != ''"
                    )
                    chem_rows = cursor.fetchall()
                    for chem_id, types_str in chem_rows:
                        type_names = [t.strip() for t in types_str.split(',') if t.strip()]
                        for type_name in type_names:
                            cursor.execute("SELECT id FROM reagent_type WHERE name = ?", (type_name,))
                            type_row = cursor.fetchone()
                            if type_row:
                                cursor.execute(
                                    "INSERT OR IGNORE INTO chemical_reagent_type (chemical_id, type_id) VALUES (?, ?)",
                                    (chem_id, type_row[0])
                                )
                    logger.info("迁移完成：chemical_reagent_type 关联表数据已从 CSV 填充")

        except Exception as e:
            # schema 迁移失败不能继续启动，否则会在运行期以更难排查的方式报错
            logger.error(f"数据库迁移执行异常: {str(e)}", exception=e)
            raise

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
            # DROP/重建表会连带删除原触发器，必须重新创建
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_chemical_info_updated_at
                AFTER UPDATE ON chemical_info
                FOR EACH ROW
                BEGIN
                    UPDATE chemical_info SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END;
            """)

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
        """事务上下文管理器（支持嵌套；嵌套段使用 SAVEPOINT 保证原子回滚）

        用法::

            with db.transaction():
                db.execute_insert(...)
                db.execute_update(...)

        进入时若不在事务中则 BEGIN；正常退出 COMMIT，异常 ROLLBACK。
        嵌套段使用 SAVEPOINT：正常退出 RELEASE（并入外层事务），异常时
        ROLLBACK TO + RELEASE——仅撤销本段写入。

        为何不用「嵌套只跳过回滚」：批量操作（如 bulk_assign_manager）外层
        单事务包裹、内层逐项 best-effort 失败时，旧实现会让失败项的半截写入
        （如瓶已更新、变更历史未写入）被外层 COMMIT 落库，造成数据不一致
        （QA 审查发现）。SAVEPOINT 让失败项的影响范围收敛在自身。

        依赖连接使用 autocommit 模式（isolation_level=None）。
        """
        # 整个事务临界区持有可重入锁：同一连接被多个 Streamlit 会话共享时，
        # 防止线程 A 的事务中混入线程 B 的语句、或 B 的 SAVEPOINT 挂到 A 的事务上。
        # 内层 execute_* 会再次获取同一把 RLock（同线程可重入），不会死锁。
        with self._lock:
            conn = self.connection
            nested = self._transaction_depth > 0
            self._transaction_depth += 1
            savepoint = f"sp_tx_{self._transaction_depth}"
            try:
                if not nested:
                    # IMMEDIATE：进入事务即取得写锁，避免读事务升级写锁时的竞争
                    conn.execute("BEGIN IMMEDIATE")
                else:
                    conn.execute(f"SAVEPOINT {savepoint}")
                yield conn
                if not nested:
                    conn.commit()
                else:
                    conn.execute(f"RELEASE {savepoint}")
            except Exception:
                if not nested:
                    conn.rollback()
                else:
                    # 仅回滚本嵌套段的写入（回滚后释放保存点，外层事务继续）
                    conn.execute(f"ROLLBACK TO {savepoint}")
                    conn.execute(f"RELEASE {savepoint}")
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
            with self._lock:
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
            with self._lock:
                cursor = self.connection.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                # 仅在未处于显式事务中时自动提交（跨表事务请使用 transaction()）
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
            with self._lock:
                cursor = self.connection.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                # 仅在未处于显式事务中时自动提交（跨表事务请使用 transaction()）
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


# ============================================================================
# 四库分离：辅助库初始化（日志库 / 附件索引库 / 归档冷库）
# app.py 启动时调用 init_aux_databases()，各初始化函数幂等、可重复执行
# ============================================================================

def init_log_db() -> Database:
    """初始化审计日志库（operation_log.db），并迁移主库历史日志

    幂等：表已存在则跳过建表；主库 operation_log 有历史数据且
    日志库为空时一次性迁移（迁移后主库表保留只读，兼容旧查询入口）。
    """
    from config.settings import DB_LOG_PATH, DB_MAIN_PATH
    log_db = Database(DB_LOG_PATH)
    cursor = log_db.connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT,
            action TEXT,
            target_type TEXT,
            target_id TEXT,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_log_time ON operation_log(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_log_action ON operation_log(action)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_log_operator ON operation_log(operator)")

    # 一次性历史迁移：日志库为空且主库有数据时复制
    cursor.execute("SELECT COUNT(*) FROM operation_log")
    if cursor.fetchone()[0] == 0:
        main_db = Database(DB_MAIN_PATH)
        if main_db.table_exists("operation_log"):
            rows = main_db.execute_query("SELECT * FROM operation_log ORDER BY id")
            if rows:
                cursor.executemany(
                    "INSERT INTO operation_log (id, operator, action, target_type, target_id, detail, created_at)"
                    " VALUES (:id, :operator, :action, :target_type, :target_id, :detail, :created_at)",
                    rows,
                )
                logger.info(f"审计日志历史迁移完成: {len(rows)} 条 → {DB_LOG_PATH}")
    log_db.connection.commit()
    return log_db


def init_attach_db() -> Database:
    """初始化附件索引库（attach_cold.db）

    附件物理文件存放在 attachments/ 目录，本库仅存文件索引元数据，
    与业务库解耦，附件下载不依赖主业务库在线。
    """
    from config.settings import DB_ATTACH_PATH
    attach_db = Database(DB_ATTACH_PATH)
    attach_db.connection.cursor().execute("""
        CREATE TABLE IF NOT EXISTS attachment_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stored_name TEXT NOT NULL UNIQUE,
            original_name TEXT,
            category TEXT,
            ref_type TEXT,
            ref_id TEXT,
            size_bytes INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    attach_db.connection.commit()
    return attach_db


def init_archive_db() -> Database:
    """初始化归档冷库（archive_cold.db）

    记录归档批次元数据；具体的过期数据搬运逻辑见 docs/架构演进规划.md。
    """
    from config.settings import DB_ARCHIVE_PATH
    archive_db = Database(DB_ARCHIVE_PATH)
    archive_db.connection.cursor().execute("""
        CREATE TABLE IF NOT EXISTS archive_batch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_table TEXT NOT NULL,
            row_count INTEGER,
            archive_year TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    archive_db.connection.commit()
    return archive_db


def init_aux_databases() -> dict:
    """初始化三个辅助库（app 启动时调用，幂等）

    Returns:
        各库文件路径字典（取自 config.settings，与实际连接路径一致）
    """
    from config.settings import DB_MAIN_PATH, DB_LOG_PATH, DB_ATTACH_PATH, DB_ARCHIVE_PATH
    init_log_db()
    init_attach_db()
    init_archive_db()
    logger.info("四库分离辅助库初始化完成（log/attach/archive）")
    return {
        "main": DB_MAIN_PATH,
        "log": DB_LOG_PATH,
        "attach": DB_ATTACH_PATH,
        "archive": DB_ARCHIVE_PATH,
    }
