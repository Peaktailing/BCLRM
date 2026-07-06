"""密码初始化脚本

为数据库中所有现有用户设置默认密码。
使用方法：python scripts/init_passwords.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.base.person_service import person_service
from db.database import Database

DEFAULT_PASSWORD = "926495@ph"


def init_all_passwords():
    """为所有现有用户设置默认密码"""
    db = Database()
    db.init_tables()

    all_persons = person_service.get_all_persons()

    if not all_persons:
        print("数据库中没有用户，请先添加用户")
        return

    print(f"找到 {len(all_persons)} 个用户，开始设置默认密码...")
    print(f"默认密码: {DEFAULT_PASSWORD}")
    print("-" * 50)

    success_count = 0
    skip_count = 0

    for person in all_persons:
        if person.password_hash:
            print(f"⏭️  用户 {person.name} 已有密码，跳过")
            skip_count += 1
            continue

        result = person_service.update_password(person.name, DEFAULT_PASSWORD)
        if result:
            print(f"✅ 用户 {person.name} ({person.role or 'user'}) 密码设置成功")
            success_count += 1
        else:
            print(f"❌ 用户 {person.name} 密码设置失败")

    print("-" * 50)
    print(f"完成：成功 {success_count} 个，跳过 {skip_count} 个")
    print(f"所有用户统一密码：{DEFAULT_PASSWORD}")


if __name__ == "__main__":
    init_all_passwords()
