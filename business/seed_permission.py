"""种子数据 - 测试账号和关联关系

四层权限系统的预置测试数据。
"""
from db.database import db
from utils.error_handler import logger

# 格式: (user_id, name, password, role, department, work_id, display_name)
SEED_USERS = [
    ("SA001", "系统管理员", "admin123", "super_admin", "系统管理部", "root", "系统管理员"),
    ("AD001", "张管理", "123456", "admin", "化学实验室", "zhang", "张管理"),
    ("AD002", "李管理", "123456", "admin", "生物实验室", "li", "李管理"),
    ("TE001", "王教授", "123456", "teacher", "化学系", "wang", "王教授"),
    ("TE002", "赵教授", "123456", "teacher", "生物系", "zhao", "赵教授"),
    ("ST001", "小学生", "123456", "student", "化学系", "stu1", "小学生"),
    ("ST002", "中学生", "123456", "student", "生物系", "stu2", "中学生"),
]

# 用户-管理员关联: (user_id, admin_id)
SEED_USER_ADMIN = [
    ("TE001", "AD001"),  # 王教授 → 张管理
    ("ST001", "AD001"),  # 小学生 → 张管理
    ("TE002", "AD002"),  # 赵教授 → 李管理
    ("ST002", "AD002"),  # 中学生 → 李管理
]


def seed_permission_data():
    """插入权限系统种子数据"""
    try:
        cursor = db.connection.cursor()

        # 插入用户
        for uid, name, pwd, role, dept, work_id, dn in SEED_USERS:
            cursor.execute(
                """INSERT OR IGNORE INTO person
                   (user_id, name, password, role, department, student_or_work_id, display_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (uid, name, pwd, role, dept, work_id, dn),
            )

        # 插入用户-管理员关联
        for uid, aid in SEED_USER_ADMIN:
            cursor.execute(
                "INSERT OR IGNORE INTO user_admin (user_id, admin_id) VALUES (?, ?)",
                (uid, aid),
            )

        db.connection.commit()
        logger.info("权限种子数据插入完成")
        return True
    except Exception as e:
        db.connection.rollback()
        logger.error(f"种子数据插入失败: {e}", exception=e)
        return False


def init_permission_system():
    """初始化权限系统（数据库迁移 + 种子数据）"""
    db.init_tables()
    seed_permission_data()
    logger.info("权限系统初始化完成")