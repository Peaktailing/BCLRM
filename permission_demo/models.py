"""数据模型定义

四层分级权限系统 v2 的数据模型：
- 用户: user_id(唯一字符串PK), name, work_id(登录), password, role, department
- 用户-管理员关联: 多对多，一个用户可从属于多个管理员
- 试剂瓶: 核心主表
- 借还记录: 审批流
"""

import sqlite3
import os
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), "permission_demo.db")


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class User:
    """系统用户"""
    user_id: str                       # 唯一字符串主键，如 "SA001"
    name: str                          # 用户名称
    work_id: str                       # 工号（用于登录）
    password: str                      # 登录密码
    role: str = "student"              # 角色: super_admin/admin/teacher/student
    department: str = ""               # 部门
    display_name: str = ""             # 显示名称（可选）
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name

    @property
    def id(self):
        """兼容旧版接口"""
        return self.user_id


@dataclass
class ReagentBottle:
    """试剂瓶"""
    bottle_number: int                 # 瓶号（唯一）
    reagent_name: str                  # 试剂名称
    cas_number: str = ""               # CAS 号
    specification: str = ""            # 规格
    quantity: float = 0.0              # 剩余量
    unit: str = "g"                    # 单位
    storage_location: str = ""         # 存储位置
    creator: str = ""                  # 创建者（管理员user_id）
    creator_name: str = ""             # 创建者显示名称
    is_controlled: bool = False        # 是否管控试剂
    id: Optional[int] = None           # 自增主键
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class BorrowRecord:
    """领用记录"""
    record_number: str                 # 记录编号
    bottle_number: int                 # 试剂瓶号
    reagent_name: str                  # 试剂名称
    borrower: str                      # 借用人（user_id）
    borrower_name: str = ""            # 借用人显示名称
    quantity: float = 0.0              # 借用量
    borrow_time: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    status: str = "待审批"              # 状态: 待审批 / 已批准 / 已拒绝
    approver: str = ""                 # 审批人（user_id）
    approver_name: str = ""            # 审批人显示名称
    approve_time: str = ""             # 审批时间
    id: Optional[int] = None           # 自增主键


# ── 数据库初始化 ──────────────────────────────────────────


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            work_id TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL DEFAULT '123456',
            role TEXT NOT NULL DEFAULT 'student',
            department TEXT DEFAULT '',
            display_name TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS user_admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            admin_id TEXT NOT NULL,
            UNIQUE(user_id, admin_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (admin_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reagent_bottles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bottle_number INTEGER NOT NULL UNIQUE,
            reagent_name TEXT NOT NULL,
            cas_number TEXT DEFAULT '',
            specification TEXT DEFAULT '',
            quantity REAL DEFAULT 0.0,
            unit TEXT DEFAULT 'g',
            storage_location TEXT DEFAULT '',
            creator TEXT DEFAULT '',
            creator_name TEXT DEFAULT '',
            is_controlled INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS borrow_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_number TEXT NOT NULL UNIQUE,
            bottle_number INTEGER NOT NULL,
            reagent_name TEXT DEFAULT '',
            borrower TEXT NOT NULL,
            borrower_name TEXT DEFAULT '',
            quantity REAL DEFAULT 0.0,
            borrow_time TEXT DEFAULT (datetime('now','localtime')),
            status TEXT DEFAULT '待审批',
            approver TEXT DEFAULT '',
            approver_name TEXT DEFAULT '',
            approve_time TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        CREATE INDEX IF NOT EXISTS idx_users_work_id ON users(work_id);
        CREATE INDEX IF NOT EXISTS idx_user_admin_user ON user_admin(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_admin_admin ON user_admin(admin_id);
        CREATE INDEX IF NOT EXISTS idx_bottles_creator ON reagent_bottles(creator);
        CREATE INDEX IF NOT EXISTS idx_borrows_borrower ON borrow_records(borrower);
        CREATE INDEX IF NOT EXISTS idx_borrows_status ON borrow_records(status);
    """)

    conn.commit()
    conn.close()


# ── 种子数据 ──────────────────────────────────────────────

# 格式: (user_id, name, work_id, password, role, department)
SEED_USERS = [
    ("SA001", "系统管理员", "root", "admin123", "super_admin", "系统管理部"),
    ("AD001", "张管理", "zhang", "123456", "admin", "化学实验室"),
    ("AD002", "李管理", "li", "123456", "admin", "生物实验室"),
    ("TE001", "王教授", "wang", "123456", "teacher", "化学系"),
    ("TE002", "赵教授", "zhao", "123456", "teacher", "生物系"),
    ("ST001", "小学生", "stu1", "123456", "student", "化学系"),
    ("ST002", "中学生", "stu2", "123456", "student", "生物系"),
]

# 用户-管理员关联: (user_id, admin_id)
# 王教授/小学生归属张管理；赵教授/中学生归属李管理
SEED_USER_ADMIN = [
    ("TE001", "AD001"),  # 王教授 → 张管理
    ("ST001", "AD001"),  # 小学生 → 张管理
    ("TE002", "AD002"),  # 赵教授 → 李管理
    ("ST002", "AD002"),  # 中学生 → 李管理
]


def seed_data():
    """插入测试种子数据"""
    conn = get_connection()
    cursor = conn.cursor()

    # 插入用户
    for uid, name, work_id, pwd, role, dept in SEED_USERS:
        cursor.execute(
            """INSERT OR IGNORE INTO users
               (user_id, name, work_id, password, role, department, display_name)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uid, name, work_id, pwd, role, dept, name),
        )

    # 插入用户-管理员关联
    for uid, aid in SEED_USER_ADMIN:
        cursor.execute(
            "INSERT OR IGNORE INTO user_admin (user_id, admin_id) VALUES (?, ?)",
            (uid, aid),
        )

    # 插入试剂瓶（creator 用 user_id，creator_name 为显示名）
    sample_reagents = [
        (1001, "无水乙醇", "64-17-5", "500ml", 500.0, "ml", "A-01", "AD001", "张管理", False),
        (1002, "浓盐酸", "7647-01-0", "500ml", 450.0, "ml", "B-02", "AD001", "张管理", True),
        (1003, "氢氧化钠", "1310-73-2", "500g", 500.0, "g", "C-03", "AD002", "李管理", False),
        (1004, "丙酮", "67-64-1", "500ml", 300.0, "ml", "A-04", "AD002", "李管理", True),
        (1005, "硫酸", "7664-93-9", "500ml", 500.0, "ml", "B-05", "AD001", "张管理", True),
        (1006, "去离子水", "", "5L", 5000.0, "ml", "D-06", "AD002", "李管理", False),
        (1007, "甲醇", "67-56-1", "500ml", 400.0, "ml", "A-07", "AD001", "张管理", True),
        (1008, "氯化钠", "7647-14-5", "500g", 500.0, "g", "C-08", "AD002", "李管理", False),
    ]

    for bn, rn, cas, spec, qty, unit, loc, creator, cname, ctrl in sample_reagents:
        cursor.execute(
            """INSERT OR IGNORE INTO reagent_bottles
               (bottle_number, reagent_name, cas_number, specification, quantity, unit,
                storage_location, creator, creator_name, is_controlled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bn, rn, cas, spec, qty, unit, loc, creator, cname, 1 if ctrl else 0),
        )

    conn.commit()
    conn.close()