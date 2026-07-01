"""种子数据 - 测试账号和关联关系（密码哈希存储）"""
from db.database import db
from utils.error_handler import logger
from utils.password_hash import hash_password

# 格式: (user_id, name, password_plain, role, department, work_id, display_name, phone)
SEED_USERS = [
    ("SA001", "系统管理员", "SysAdmin@2024", "super_admin", "系统管理部", "root", "系统管理员", "13800000001"),
    ("AD001", "张管理", "Zhang@1234", "admin", "化学实验室", "zhang", "张管理", "13800000002"),
    ("AD002", "李管理", "LiManager@12", "admin", "生物实验室", "li", "李管理", "13800000003"),
    ("TE001", "王教授", "Wang@1234", "teacher", "化学系", "wang", "王教授", "13800000004"),
    ("TE002", "赵教授", "Zhao@1234", "teacher", "生物系", "zhao", "赵教授", "13800000005"),
    ("ST001", "小学生", "Student@12", "student", "化学系", "stu1", "小学生", "13800000006"),
    ("ST002", "中学生", "Student@12", "student", "生物系", "stu2", "中学生", "13800000007"),
]

SEED_USER_ADMIN = [
    ("TE001", "AD001"),
    ("ST001", "AD001"),
    ("TE002", "AD002"),
    ("ST002", "AD002"),
]


def seed_permission_data():
    """插入权限系统种子数据"""
    try:
        cursor = db.connection.cursor()
        for uid, name, pwd, role, dept, work_id, dn, phone in SEED_USERS:
            cursor.execute(
                """INSERT OR IGNORE INTO person
                   (user_id, name, password, role, department, student_or_work_id, display_name, phone)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, name, hash_password(pwd), role, dept, work_id, dn, phone),
            )
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
    """初始化权限系统"""
    db.init_tables()
    seed_permission_data()
    logger.info("权限系统初始化完成")