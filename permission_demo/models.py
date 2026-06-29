"""数据模型定义

四层分级权限系统的数据模型，包括用户、试剂瓶、借还记录。
使用 Python dataclass + SQLite 存储。
"""

import sqlite3
import os
from dataclasses import dataclass, field, asdict
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
    name: str                          # 用户名
    role: str = "student"              # 角色: super_admin / admin / teacher / student
    display_name: str = ""             # 显示名称
    department: str = ""               # 部门
    id: Optional[int] = None           # 自增主键
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name


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
    creator: str = ""                  # 创建者（录入人）
    is_controlled: bool = False        # 是否管控试剂
    id: Optional[int] = None           # 自增主键
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class BorrowRecord:
    """领用记录"""
    record_number: str                 # 记录编号
    bottle_number: int                 # 试剂瓶号
    reagent_name: str                  # 试剂名称
    borrower: str                      # 借用人
    quantity: float = 0.0              # 借用量
    borrow_time: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    status: str = "待审批"              # 状态: 待审批 / 已批准 / 已拒绝
    approver: str = ""                 # 审批人
    approve_time: str = ""             # 审批时间
    id: Optional[int] = None           # 自增主键


# ── 数据库操作 ────────────────────────────────────────────


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'student',
            display_name TEXT DEFAULT '',
            department TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
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
            is_controlled INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS borrow_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_number TEXT NOT NULL UNIQUE,
            bottle_number INTEGER NOT NULL,
            reagent_name TEXT DEFAULT '',
            borrower TEXT NOT NULL,
            quantity REAL DEFAULT 0.0,
            borrow_time TEXT DEFAULT (datetime('now','localtime')),
            status TEXT DEFAULT '待审批',
            approver TEXT DEFAULT '',
            approve_time TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        CREATE INDEX IF NOT EXISTS idx_bottles_creator ON reagent_bottles(creator);
        CREATE INDEX IF NOT EXISTS idx_borrows_borrower ON borrow_records(borrower);
        CREATE INDEX IF NOT EXISTS idx_borrows_status ON borrow_records(status);
    """)

    conn.commit()
    conn.close()


# ── 种子数据 ──────────────────────────────────────────────


SEED_USERS = [
    ("super_admin", "超级管理员", "root", "系统管理部"),
    ("admin", "管理员", "张管理", "化学实验室"),
    ("admin", "管理员", "李管理", "生物实验室"),
    ("teacher", "教师", "王教授", "化学系"),
    ("teacher", "教师", "赵教授", "生物系"),
    ("student", "学生", "小学生", "化学系"),
    ("student", "学生", "中学生", "生物系"),
]


def seed_data():
    """插入测试种子数据"""
    conn = get_connection()
    cursor = conn.cursor()

    # 插入用户
    for role, display_name, name, dept in SEED_USERS:
        cursor.execute(
            "INSERT OR IGNORE INTO users (name, role, display_name, department) VALUES (?, ?, ?, ?)",
            (name, role, display_name, dept),
        )

    # 插入试剂瓶
    sample_reagents = [
        (1001, "无水乙醇", "64-17-5", "500ml", 500.0, "ml", "A-01", "张管理", False),
        (1002, "浓盐酸", "7647-01-0", "500ml", 450.0, "ml", "B-02", "张管理", True),
        (1003, "氢氧化钠", "1310-73-2", "500g", 500.0, "g", "C-03", "李管理", False),
        (1004, "丙酮", "67-64-1", "500ml", 300.0, "ml", "A-04", "李管理", True),
        (1005, "硫酸", "7664-93-9", "500ml", 500.0, "ml", "B-05", "张管理", True),
        (1006, "去离子水", "", "5L", 5000.0, "ml", "D-06", "李管理", False),
        (1007, "甲醇", "67-56-1", "500ml", 400.0, "ml", "A-07", "张管理", True),
        (1008, "氯化钠", "7647-14-5", "500g", 500.0, "g", "C-08", "李管理", False),
    ]

    for bn, rn, cas, spec, qty, unit, loc, creator, ctrl in sample_reagents:
        cursor.execute(
            """INSERT OR IGNORE INTO reagent_bottles
               (bottle_number, reagent_name, cas_number, specification, quantity, unit, storage_location, creator, is_controlled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bn, rn, cas, spec, qty, unit, loc, creator, 1 if ctrl else 0),
        )

    conn.commit()
    conn.close()