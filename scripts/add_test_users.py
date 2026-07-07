import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.base.person_service import person_service
from db.database import Database
from utils.password_utils import hash_password


def add_test_users():
    db = Database()
    db.init_tables()

    test_users = [
        {
            "name": "潘汉",
            "role": "super_admin",
            "department": "化学系",
            "phone": "13800138000",
            "student_or_work_id": "T2024000",
            "password": "admin123"
        },
        {
            "name": "潘汉1",
            "role": "super_admin",
            "department": "化学系",
            "phone": "13800138001",
            "student_or_work_id": "T2024001",
            "password": "admin123"
        },
        {
            "name": "潘汉2",
            "role": "admin",
            "department": "化学系",
            "phone": "13800138002",
            "student_or_work_id": "T2024002",
            "password": "admin123"
        },
        {
            "name": "潘汉3",
            "role": "teacher",
            "department": "化学系",
            "phone": "13800138003",
            "student_or_work_id": "T2024003",
            "password": "teacher123"
        }
    ]

    for user_data in test_users:
        existing = person_service.get_by_name(user_data["name"])
        password = user_data.pop("password")
        if existing:
            # 用户已存在，检查是否需要设置密码
            if not person_service.has_password(user_data["name"]):
                person_service.set_password(user_data["name"], password)
                print(f"🔑 已为用户 {user_data['name']} 设置密码")
            else:
                print(f"用户 {user_data['name']} 已存在（已设置密码），跳过")
            continue

        result = person_service.create(user_data)
        if result:
            person_service.set_password(user_data["name"], password)
            print(f"✅ 成功添加用户: {user_data['name']} ({user_data['role']})，密码已设置")
        else:
            print(f"❌ 添加用户失败: {user_data['name']}")

    print("\n=== 当前所有用户列表 ===")
    all_users = person_service.get_all_persons()
    for user in all_users:
        has_pwd = "已设置" if person_service.has_password(user.name) else "未设置"
        print(f"ID: {user.id}, 姓名: {user.name}, 角色: {user.role}, 部门: {user.department}, 工号: {user.student_or_work_id}, 密码: {has_pwd}")


if __name__ == "__main__":
    add_test_users()
