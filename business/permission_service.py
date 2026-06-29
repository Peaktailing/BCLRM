"""权限管理业务服务

提供用户权限检查、管控试剂领用权限检查等功能。

使用面向对象设计，所有权限方法封装在 PermissionService 类中。
"""
from services.base.person_service import person_service
from utils.error_handler import logger, ServiceResult


class PermissionService:
    """权限管理业务服务类

    封装所有权限检查相关的业务逻辑，包括：
    - 用户权限验证
    - 管控试剂领用权限检查
    - 管理员身份判断
    """

    # 预设的管理员用户列表
    _ADMIN_USERS = ["admin", "管理员", "潘汉", "Admin", "ADMIN"]

    def __init__(self):
        """初始化权限服务"""
        self.person_service = person_service

    def check_permission(self, user_name: str, required_role: str = "user") -> tuple:
        """检查用户权限

        Args:
            user_name: 用户名
            required_role: 需要的角色 (admin/user/guest)

        Returns:
            (是否有权限, 提示信息)
        """
        # 访客权限 - 允许基础访问
        if required_role == "guest":
            return True, "允许访问"

        # 用户权限 - 检查用户是否存在
        if required_role == "user":
            person = self.person_service.get_by_name(user_name)
            if person:
                return True, f"用户 {user_name} 验证通过"
            # 如果人员表未配置，默认允许访问
            return True, "用户验证通过（人员表未配置）"

        # 管理员权限 - 需要特殊配置
        if required_role == "admin":
            if user_name in self._ADMIN_USERS:
                return True, f"管理员 {user_name} 验证通过"
            # 也可以从数据库查询管理员角色
            person = self.person_service.get_by_name(user_name)
            if person and person.role == "admin":
                return True, f"管理员 {user_name} 验证通过"
            return False, f"用户 {user_name} 无管理员权限"

        return False, "未知权限需求"

    def can_borrow_controlled(self, user_name: str) -> tuple:
        """检查用户是否可以领用管控试剂

        Args:
            user_name: 用户名

        Returns:
            (是否允许, 提示信息)
        """
        # 检查用户是否为管理员（管理员可领用所有试剂）
        is_admin, _ = self.check_permission(user_name, "admin")
        if is_admin:
            return True, "管理员可领用管控试剂"

        # 检查用户是否有特殊审批权限（预留接口）
        # 目前默认允许所有用户领用管控试剂
        # 实际使用时可根据审批流程进行限制

        return True, "允许领用管控试剂（需后续审批）"

    def is_admin(self, user_name: str) -> bool:
        """判断用户是否为管理员

        Args:
            user_name: 用户名

        Returns:
            是否为管理员
        """
        result, _ = self.check_permission(user_name, "admin")
        return result


# 全局单例实例
permission_service = PermissionService()