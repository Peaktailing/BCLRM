"""权限管理业务服务

提供用户权限检查、管控试剂领用权限检查等功能。
"""
from services.base.person_service import person_service

def check_permission(user_name: str, required_role: str = "user") -> tuple[bool, str]:
    """
    检查用户权限
    
    参数：
        user_name: 用户名
        required_role: 需要的角色 (admin/user/guest)
    
    返回：
        (是否有权限, 提示信息)
    """
    # 访客权限 - 允许基础访问
    if required_role == "guest":
        return True, "允许访问"
    
    # 用户权限 - 检查用户是否存在
    if required_role == "user":
        person = person_service.get_by_name(user_name)
        if person:
            return True, f"用户 {user_name} 验证通过"
        # 如果人员表未配置，默认允许访问
        return True, "用户验证通过（人员表未配置）"
    
    # 管理员权限 - 需要特殊配置
    if required_role == "admin":
        # 预设的管理员用户列表
        admin_users = ["admin", "管理员", "潘汉", "Admin", "ADMIN"]
        if user_name in admin_users:
            return True, f"管理员 {user_name} 验证通过"
        # 也可以从数据库查询管理员角色
        person = person_service.get_by_name(user_name)
        if person and person.role == "admin":
            return True, f"管理员 {user_name} 验证通过"
        return False, f"❌ 用户 {user_name} 无管理员权限"
    
    return False, "❌ 未知权限需求"

def can_borrow_controlled(user_name: str) -> tuple[bool, str]:
    """
    检查用户是否可以领用管控试剂
    
    参数：
        user_name: 用户名
    
    返回：
        (是否允许, 提示信息)
    """
    # 检查用户是否为管理员（管理员可领用所有试剂）
    is_admin, _ = check_permission(user_name, "admin")
    if is_admin:
        return True, "管理员可领用管控试剂"
    
    # 检查用户是否有特殊审批权限（预留接口）
    # 目前默认允许所有用户领用管控试剂
    # 实际使用时可根据审批流程进行限制
    
    return True, "允许领用管控试剂（需后续审批）"

def is_admin(user_name: str) -> bool:
    """
    判断用户是否为管理员
    
    参数：
        user_name: 用户名
    
    返回：
        是否为管理员
    """
    result, _ = check_permission(user_name, "admin")
    return result