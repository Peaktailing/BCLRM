"""安全修复验证脚本

验证所有安全修复是否正确实施。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.base.person_service import person_service
from db.database import Database
from utils.password_utils import hash_password, verify_password


def test_password_hash():
    """测试密码哈希和验证功能"""
    print("=" * 60)
    print("测试 1: 密码哈希和验证功能")
    print("=" * 60)

    test_password = "926495@ph"
    hashed = hash_password(test_password)
    print(f"  原始密码: {test_password}")
    print(f"  哈希结果: {hashed[:60]}...")

    assert verify_password(test_password, hashed), "密码验证应该通过"
    print("  ✅ 正确密码验证通过")

    assert not verify_password("wrong_password", hashed), "错误密码应该验证失败"
    print("  ✅ 错误密码验证失败")

    assert not verify_password(test_password, None), "None 哈希应该验证失败"
    print("  ✅ None 哈希验证失败")

    print("  ✅ 密码哈希测试全部通过\n")


def test_database_migration():
    """测试数据库迁移是否添加了 password_hash 字段"""
    print("=" * 60)
    print("测试 2: 数据库迁移 - password_hash 字段")
    print("=" * 60)

    db = Database()
    db.init_tables()

    cursor = db.connection.cursor()
    cursor.execute("PRAGMA table_info(person)")
    columns = {row[1] for row in cursor.fetchall()}

    assert "password_hash" in columns, "person 表应该有 password_hash 字段"
    print("  ✅ person 表包含 password_hash 字段\n")


def test_person_service_password():
    """测试 person_service 的密码相关方法"""
    print("=" * 60)
    print("测试 3: PersonService 密码方法")
    print("=" * 60)

    # 测试创建带密码的用户
    new_id = person_service.create_with_password(
        name="test_user_001",
        password="test123",
        role="user"
    )
    assert new_id is not None, "应该能创建带密码的用户"
    print(f"  ✅ 创建带密码的用户成功，ID: {new_id}")

    # 测试验证密码
    assert person_service.verify_user_password("test_user_001", "test123"), "正确密码应该验证通过"
    print("  ✅ 正确密码验证通过")

    assert not person_service.verify_user_password("test_user_001", "wrong"), "错误密码应该验证失败"
    print("  ✅ 错误密码验证失败")

    assert not person_service.verify_user_password("nonexistent", "test123"), "不存在用户应该验证失败"
    print("  ✅ 不存在用户验证失败")

    # 测试更新密码
    assert person_service.update_password("test_user_001", "newpassword456"), "应该能更新密码"
    print("  ✅ 更新密码成功")

    assert not person_service.verify_user_password("test_user_001", "test123"), "旧密码应该失效"
    print("  ✅ 旧密码已失效")

    assert person_service.verify_user_password("test_user_001", "newpassword456"), "新密码应该生效"
    print("  ✅ 新密码生效")

    # 清理测试用户
    person = person_service.get_by_name("test_user_001")
    if person:
        person_service.delete(person.id)
        print("  ✅ 清理测试用户")

    print("  ✅ PersonService 密码测试全部通过\n")


def test_default_users_password():
    """测试默认用户密码是否设置正确"""
    print("=" * 60)
    print("测试 4: 现有用户密码验证")
    print("=" * 60)

    all_persons = person_service.get_all_persons()
    print(f"  数据库中共有 {len(all_persons)} 个用户")

    default_password = "926495@ph"
    success_count = 0

    for person in all_persons:
        if person.password_hash:
            ok = verify_password(default_password, person.password_hash)
            if ok:
                print(f"  ✅ 用户 {person.name} ({person.role}) 密码验证通过")
                success_count += 1
            else:
                print(f"  ⚠️ 用户 {person.name} 密码不是默认密码")
        else:
            print(f"  ❌ 用户 {person.name} 没有设置密码")

    print(f"\n  总计: {success_count}/{len(all_persons)} 个用户设置了默认密码\n")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("安全修复验证脚本")
    print("=" * 60 + "\n")

    try:
        test_password_hash()
        test_database_migration()
        test_person_service_password()
        test_default_users_password()

        print("=" * 60)
        print("🎉 所有安全修复验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
