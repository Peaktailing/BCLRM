"""权限管理业务服务

提供用户权限检查、管控试剂领用权限检查等功能。

使用面向对象设计，所有权限方法封装在 PermissionService 类中。

四层权限系统：
- super_admin: 超级管理员，拥有所有权限
- admin: 管理员，拥有管理权限
- teacher: 教师，拥有领用和管理权限
- user: 普通用户，拥有基础访问权限

所有对外方法统一返回 ServiceResult：
- 查询类（check_permission / can_borrow_controlled / is_admin 等）data 为 bool
- get_user_role 的 data 为角色字符串
- 失败场景（异常）统一返回 ServiceResult.fail
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

    def check_permission(self, user_name: str, required_role: str = "user") -> ServiceResult:
        """检查用户权限

        Args:
            user_name: 用户名
            required_role: 需要的角色 (super_admin/admin/teacher/user/guest)

        Returns:
            ServiceResult[bool] - data 表示是否拥有所需权限，message 为描述
        """
        try:
            if required_role == "guest":
                return ServiceResult.ok(data=True, message="允许访问")

            person = self.person_service.get_by_name(user_name)
            if not person:
                return ServiceResult.ok(
                    data=False,
                    message="用户验证失败：用户名不存在或人员表未配置，请联系管理员",
                )

            user_role = person.role or "user"

            if required_role == "user":
                return ServiceResult.ok(data=True, message=f"用户 {user_name} 验证通过")

            if required_role == "teacher":
                allowed = user_role in self.TEACHER_ROLES
                return ServiceResult.ok(
                    data=allowed,
                    message=f"教师 {user_name} 验证通过" if allowed else f"用户 {user_name} 无教师权限",
                )

            if required_role == "admin":
                allowed = user_role in self.ADMIN_ROLES
                return ServiceResult.ok(
                    data=allowed,
                    message=f"管理员 {user_name} 验证通过" if allowed else f"用户 {user_name} 无管理员权限",
                )

            if required_role == "super_admin":
                allowed = user_role == "super_admin"
                return ServiceResult.ok(
                    data=allowed,
                    message=f"超级管理员 {user_name} 验证通过" if allowed else f"用户 {user_name} 无超级管理员权限",
                )

            return ServiceResult.ok(data=False, message="未知权限需求")
        except Exception as e:
            logger.error("权限检查异常", user_name=user_name, exception=e)
            return ServiceResult.fail(message=f"权限检查失败: {str(e)}", error_code="PERMISSION_CHECK_ERROR")

    def can_borrow_controlled(self, user_name: str) -> ServiceResult:
        """检查用户是否可以领用管控试剂

        Args:
            user_name: 用户名

        Returns:
            ServiceResult[bool] - data 表示是否允许，message 为描述
        """
        try:
            is_admin = self.check_permission(user_name, "admin").data
            if is_admin:
                return ServiceResult.ok(data=True, message="管理员可领用管控试剂")

            is_teacher = self.check_permission(user_name, "teacher").data
            if is_teacher:
                return ServiceResult.ok(data=True, message="教师可领用管控试剂（需审批）")

            return ServiceResult.ok(data=False, message="普通用户不允许领用管控试剂")
        except Exception as e:
            logger.error("管控权限检查异常", user_name=user_name, exception=e)
            return ServiceResult.fail(message=f"管控权限检查失败: {str(e)}")

    def is_admin(self, user_name: str) -> ServiceResult:
        """判断用户是否为管理员（包含超级管理员）

        Returns:
            ServiceResult[bool]
        """
        try:
            return ServiceResult.ok(data=bool(self.check_permission(user_name, "admin").data))
        except Exception as e:
            return ServiceResult.fail(message=str(e))

    def is_super_admin(self, user_name: str) -> ServiceResult:
        """判断用户是否为超级管理员

        Returns:
            ServiceResult[bool]
        """
        try:
            return ServiceResult.ok(data=bool(self.check_permission(user_name, "super_admin").data))
        except Exception as e:
            return ServiceResult.fail(message=str(e))

    def is_teacher(self, user_name: str) -> ServiceResult:
        """判断用户是否为教师及以上角色

        Returns:
            ServiceResult[bool]
        """
        try:
            return ServiceResult.ok(data=bool(self.check_permission(user_name, "teacher").data))
        except Exception as e:
            return ServiceResult.fail(message=str(e))

    def get_user_role(self, user_name: str) -> ServiceResult:
        """获取用户角色

        Returns:
            ServiceResult[str] - data 为角色字符串，默认 "user"
        """
        try:
            person = self.person_service.get_by_name(user_name)
            if not person:
                return ServiceResult.ok(data="user")
            return ServiceResult.ok(data=person.role or "user")
        except Exception as e:
            return ServiceResult.fail(message=str(e))


# 全局单例实例
permission_service = PermissionService()
