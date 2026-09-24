from business.permission_service import permission_service


def test_permissions():
    test_users = [
        ("潘汉", "super_admin"),
        ("潘汉1", "super_admin"),
        ("潘汉2", "admin"),
        ("潘汉3", "teacher"),
        ("不存在的用户", "user")
    ]

    print("=== 四层权限系统测试 ===\n")

    for user_name, expected_role in test_users:
        print(f"\n--- 测试用户: {user_name} (预期角色: {expected_role}) ---")

        print("\n1. 用户权限检查 (required_role='user'):")
        r = permission_service.check_permission(user_name, "user")
        print(f"   结果: {'✅ 有权限' if r.data else '❌ 无权限'} - {r.message}")

        print("\n2. 教师权限检查 (required_role='teacher'):")
        r = permission_service.check_permission(user_name, "teacher")
        print(f"   结果: {'✅ 有权限' if r.data else '❌ 无权限'} - {r.message}")

        print("\n3. 管理员权限检查 (required_role='admin'):")
        r = permission_service.check_permission(user_name, "admin")
        print(f"   结果: {'✅ 有权限' if r.data else '❌ 无权限'} - {r.message}")

        print("\n4. 超级管理员权限检查 (required_role='super_admin'):")
        r = permission_service.check_permission(user_name, "super_admin")
        print(f"   结果: {'✅ 有权限' if r.data else '❌ 无权限'} - {r.message}")

        print("\n5. 角色判断方法:")
        print(f"   is_admin(): {permission_service.is_admin(user_name).data}")
        print(f"   is_super_admin(): {permission_service.is_super_admin(user_name).data}")
        print(f"   is_teacher(): {permission_service.is_teacher(user_name).data}")
        print(f"   get_user_role(): {permission_service.get_user_role(user_name).data}")

        print("\n6. 管控试剂领用权限:")
        r = permission_service.can_borrow_controlled(user_name)
        print(f"   结果: {'✅ 允许' if r.data else '❌ 拒绝'} - {r.message}")


if __name__ == "__main__":
    test_permissions()
