"""权限管理业务服务

提供用户权限检查、管控试剂领用权限检查等功能。

使用面向对象设计，所有权限方法封装在 PermissionService 类中。

四层权限系统：
- super_admin: 超级管理员，拥有所有权限
- admin: 管理员，拥有管理权限
- teacher: 教师，拥有领用和管理权限
- user: 普通用户，拥有基础访问权限
"""
from services.base.person_service import person_service
from utils.error_handler import logger, ServiceResult


class PermissionService:
    """权限管理业务服务类

    封装所有权限检查相关的业务逻辑，包括：
    - 用户权限验证
    - 管控试剂领用权限检查
    - 管理员身份判断
    - 超级管理员身份判断

    角色通过数据库 person.role 字段判定：
    - super_admin: 超级管理员
    - admin: 管理员
    - teacher: 教师
    - user: 普通用户
    """

    ADMIN_ROLES = {"super_admin", "admin"}
    TEACHER_ROLES = {"super_admin", "admin", "teacher"}

    def __init__(self, person_service=None):
        """初始化权限服务

        Args:
            person_service: PersonService 实例，None 则使用全局单例
        """
        from services.base.person_service import person_service as module_person_service
        self.person_service = person_service or module_person_service

    def check_permission(self, user_name: str, required_role: str = "user") -> tuple:
        """检查用户权限

        Args:
            user_name: 用户名
            required_role: 需要的角色 (super_admin/admin/teacher/user/guest)

        Returns:
            (是否有权限, 提示信息)
        """
        if required_role == "guest":
            return True, "允许访问"

        person = self.person_service.get_by_name(user_name)
        if not person:
            return False, "用户验证失败：用户名不存在或人员表未配置，请联系管理员"

        user_role = person.role or "user"

        if required_role == "user":
            return True, f"用户 {user_name} 验证通过"

        if required_role == "teacher":
            if user_role in self.TEACHER_ROLES:
                return True, f"教师 {user_name} 验证通过"
            return False, f"用户 {user_name} 无教师权限"

        if required_role == "admin":
            if user_role in self.ADMIN_ROLES:
                return True, f"管理员 {user_name} 验证通过"
            return False, f"用户 {user_name} 无管理员权限"

        if required_role == "super_admin":
            if user_role == "super_admin":
                return True, f"超级管理员 {user_name} 验证通过"
            return False, f"用户 {user_name} 无超级管理员权限"

        return False, "未知权限需求"

    def can_borrow_controlled(self, user_name: str) -> tuple:
        """检查用户是否可以领用管控试剂

        Args:
            user_name: 用户名

        Returns:
            (是否允许, 提示信息)
        """
        is_admin, _ = self.check_permission(user_name, "admin")
        if is_admin:
            return True, "管理员可领用管控试剂"

        is_teacher, _ = self.check_permission(user_name, "teacher")
        if is_teacher:
            return True, "教师可领用管控试剂（需审批）"

        return False, "普通用户不允许领用管控试剂"

    def is_admin(self, user_name: str) -> bool:
        """判断用户是否为管理员（包含超级管理员）

        Args:
            user_name: 用户名

        Returns:
            是否为管理员
        """
        result, _ = self.check_permission(user_name, "admin")
        return result

    def is_super_admin(self, user_name: str) -> bool:
        """判断用户是否为超级管理员

        Args:
            user_name: 用户名

        Returns:
            是否为超级管理员
        """
        result, _ = self.check_permission(user_name, "super_admin")
        return result

    def is_teacher(self, user_name: str) -> bool:
        """判断用户是否为教师及以上角色

        Args:
            user_name: 用户名

        Returns:
            是否为教师及以上角色
        """
        result, _ = self.check_permission(user_name, "teacher")
        return result

    def get_user_role(self, user_name: str) -> str:
        """获取用户角色

        Args:
            user_name: 用户名

        Returns:
            用户角色字符串
        """
        person = self.person_service.get_by_name(user_name)
        if not person:
            return "user"
        return person.role or "user"


# 全局单例实例
permission_service = PermissionService()