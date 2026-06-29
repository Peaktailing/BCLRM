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
                    user_id TEXT UNIQUE,
                    name TEXT NOT NULL UNIQUE,
                    password TEXT DEFAULT '123456',
                    role TEXT,
                    department TEXT,
                    phone TEXT,
                    student_or_work_id TEXT,
                    display_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 1.1 用户-管理员关联表（多对多）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_admin (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    admin_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, admin_id),
                    FOREIGN KEY (user_id) REFERENCES person(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (admin_id) REFERENCES person(user_id) ON DELETE CASCADE
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
                    creator TEXT,
                    creator_name TEXT,
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
                    borrow_qty REAL,
                    is_controlled INTEGER DEFAULT 0,
                    borrow_time TEXT,
                    borrow_status TEXT DEFAULT '已批准',
                    approver TEXT,
                    approver_id TEXT,
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

            # ── person 表迁移 ──
            cursor.execute("PRAGMA table_info(person)")
            person_cols = {row[1] for row in cursor.fetchall()}
            if "user_id" not in person_cols:
                cursor.execute("ALTER TABLE person ADD COLUMN user_id TEXT")
                logger.info("迁移完成：person 表添加 user_id 字段")
            if "password" not in person_cols:
                cursor.execute("ALTER TABLE person ADD COLUMN password TEXT DEFAULT '123456'")
                logger.info("迁移完成：person 表添加 password 字段")
            if "display_name" not in person_cols:
                cursor.execute("ALTER TABLE person ADD COLUMN display_name TEXT")
                logger.info("迁移完成：person 表添加 display_name 字段")

            # 确保 person.user_id 有 UNIQUE 约束（user_admin 外键引用需要）
            # SQLite 的 ALTER TABLE 不支持添加约束，需要重建表
            cursor.execute("PRAGMA index_list('person')")
            has_user_id_unique = False
            for idx in cursor.fetchall():
                # idx: (seq, name, unique, origin, partial)
                if idx[2] == 1:  # unique index
                    cursor.execute(f"PRAGMA index_info('{idx[1]}')")
                    for col in cursor.fetchall():
                        # col: (cid, name, seqno_in_index...); col[2] is column name
                        if col[2] == 'user_id':
                            has_user_id_unique = True
                            break
            if not has_user_id_unique:
                logger.info("迁移：重建 person 表以添加 user_id UNIQUE 约束")
                cursor.execute("PRAGMA foreign_keys=OFF")
                cursor.execute("""
                    CREATE TABLE person_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT UNIQUE,
                        name TEXT NOT NULL UNIQUE,
                        password TEXT DEFAULT '123456',
                        role TEXT,
                        department TEXT,
                        phone TEXT,
                        student_or_work_id TEXT,
                        display_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    INSERT INTO person_new
                        (id, user_id, name, password, role, department, phone,
                         student_or_work_id, display_name, created_at, updated_at)
                    SELECT id, user_id, name, password, role, department, phone,
                           student_or_work_id, display_name, created_at, updated_at
                    FROM person
                """)
                cursor.execute("DROP TABLE person")
                cursor.execute("ALTER TABLE person_new RENAME TO person")
                cursor.execute("PRAGMA foreign_key_check")
                cursor.execute("PRAGMA foreign_keys=ON")
                logger.info("迁移完成：person 表 user_id UNIQUE 约束已添加")

            # 为已有用户自动生成 user_id
            existing = cursor.execute("SELECT id, name, user_id, display_name FROM person").fetchall()
            for row in existing:
                pid, name, uid, dn = row
                if not uid:
                    import hashlib
                    uid = "U" + hashlib.md5(name.encode()).hexdigest()[:8].upper()
                    cursor.execute("UPDATE person SET user_id=? WHERE id=?", (uid, pid))
                if not dn:
                    cursor.execute("UPDATE person SET display_name=? WHERE id=?", (name, pid))
            self.connection.commit()

            # ── reagent_bottle 表迁移 ──
            cursor.execute("PRAGMA table_info(reagent_bottle)")
            bottle_cols = {row[1] for row in cursor.fetchall()}
            if "expired_flag" not in bottle_cols:
                cursor.execute("ALTER TABLE reagent_bottle ADD COLUMN expired_flag TEXT DEFAULT '正常'")
                logger.info("迁移完成：reagent_bottle 表添加 expired_flag 字段")
            if "creator" not in bottle_cols:
                cursor.execute("ALTER TABLE reagent_bottle ADD COLUMN creator TEXT")
                logger.info("迁移完成：reagent_bottle 表添加 creator 字段")
            if "creator_name" not in bottle_cols:
                cursor.execute("ALTER TABLE reagent_bottle ADD COLUMN creator_name TEXT")
                logger.info("迁移完成：reagent_bottle 表添加 creator_name 字段")

            # ── borrow_record 表迁移 ──
            cursor.execute("PRAGMA table_info(borrow_record)")
            borrow_cols = {row[1] for row in cursor.fetchall()}
            if "borrow_status" not in borrow_cols:
                cursor.execute("ALTER TABLE borrow_record ADD COLUMN borrow_status TEXT DEFAULT '已批准'")
                logger.info("迁移完成：borrow_record 表添加 borrow_status 字段")
            if "borrow_qty" not in borrow_cols:
                cursor.execute("ALTER TABLE borrow_record ADD COLUMN borrow_qty REAL")
                logger.info("迁移完成：borrow_record 表添加 borrow_qty 字段")
            if "approver_id" not in borrow_cols:
                cursor.execute("ALTER TABLE borrow_record ADD COLUMN approver_id TEXT")
                logger.info("迁移完成：borrow_record 表添加 approver_id 字段")

            # ── user_admin 索引 ──
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_admin_user ON user_admin(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_admin_admin ON user_admin(admin_id)")

            # ── 原有迁移 ──
            cursor.execute("PRAGMA table_info(chemical_info)")
            chem_columns = {row[1] for row in cursor.fetchall()}
            if "unsealed_shelf_life" not in chem_columns:
                cursor.execute("ALTER TABLE chemical_info ADD COLUMN unsealed_shelf_life INTEGER")
                logger.info("迁移完成：chemical_info 表添加 unsealed_shelf_life 字段")
            if "sealed_shelf_life" not in chem_columns:
                cursor.execute("ALTER TABLE chemical_info ADD COLUMN sealed_shelf_life INTEGER")
                logger.info("迁移完成：chemical_info 表添加 sealed_shelf_life 字段")

            cursor.execute("PRAGMA table_info(reagent_type)")
            rt_columns = {row[1] for row in cursor.fetchall()}
            if "default_unsealed_shelf_life" not in rt_columns:
                cursor.execute("ALTER TABLE reagent_type ADD COLUMN default_unsealed_shelf_life INTEGER")
                logger.info("迁移完成：reagent_type 表添加 default_unsealed_shelf_life 字段")
            if "default_sealed_shelf_life" not in rt_columns:
                cursor.execute("ALTER TABLE reagent_type ADD COLUMN default_sealed_shelf_life INTEGER")
                logger.info("迁移完成：reagent_type 表添加 default_sealed_shelf_life 字段")

            self.connection.commit()

            # 迁移：移除 chemical_info 表的 reagent_type 外键约束
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
        # fk 格式: (id, seq, table, from, to, on_update, on_delete, match)
        has_reagent_type_fk = any(
            fk[2] == 'reagent_type' and fk[3] == 'reagent_type'
            for fk in fks
        )

        if not has_reagent_type_fk:
            return  # 没有外键，无需迁移

        logger.info("开始迁移：移除 chemical_info 表的 reagent_type 外键约束")

        # 保存原始外键状态
        cursor.execute("PRAGMA foreign_keys")
        original_fk_state = cursor.fetchone()[0]

        try:
            # 临时关闭外键约束
            cursor.execute("PRAGMA foreign_keys = OFF")

            # 创建新表（无 reagent_type 外键）
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

            # 复制数据
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

            # 删除旧表
            cursor.execute("DROP TABLE chemical_info")

            # 重命名新表
            cursor.execute("ALTER TABLE chemical_info_new RENAME TO chemical_info")

            # 重建索引（表重建后索引会丢失）
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chemical_name ON chemical_info(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chemical_cas ON chemical_info(cas_number)")

            # 恢复外键约束状态
            cursor.execute(f"PRAGMA foreign_keys = {original_fk_state}")

            self.connection.commit()
            logger.info("迁移完成：chemical_info 表的 reagent_type 外键约束已移除，索引已重建")
        except Exception as e:
            # 迁移失败时恢复外键状态
            cursor.execute(f"PRAGMA foreign_keys = {original_fk_state}")
            self.connection.rollback()
            logger.error(f"迁移失败：{str(e)}", exc_info=True)
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