import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.base.person_service import person_service
from db.database import Database


def add_test_users():
    db = Database()
    db.init_tables()

    test_users = [
        {
            "name": "潘汉",
            "role": "super_admin",
            "department": "化学系",
            "phone": "13800138000",
            "student_or_work_id": "T2024000"
        },
        {
            "name": "潘汉1",
            "role": "super_admin",
            "department": "化学系",
            "phone": "13800138001",
            "student_or_work_id": "T2024001"
        },
        {
            "name": "潘汉2",
            "role": "admin",
            "department": "化学系",
            "phone": "13800138002",
            "student_or_work_id": "T2024002"
        },
        {
            "name": "潘汉3",
            "role": "teacher",
            "department": "化学系",
            "phone": "13800138003",
            "student_or_work_id": "T2024003"
        }
    ]

    for user_data in test_users:
        existing = person_service.get_by_name(user_data["name"])
        if existing:
            print(f"用户 {user_data['name']} 已存在，跳过")
            continue

        result = person_service.create(user_data)
        if result:
            print(f"✅ 成功添加用户: {user_data['name']} ({user_data['role']})")
        else:
            print(f"❌ 添加用户失败: {user_data['name']}")

    print("\n=== 当前所有用户列表 ===")
    all_users = person_service.get_all_persons()
    for user in all_users:
        print(f"ID: {user.id}, 姓名: {user.name}, 角色: {user.role}, 部门: {user.department}, 工号: {user.student_or_work_id}")


if __name__ == "__main__":
    add_test_users()
