"""人员服务类

对应数据表：人员信息表 (person)

提供人员信息的CRUD操作和查询方法，以及密码认证相关能力。
密码统一使用 utils/password_utils（PBKDF2-HMAC-SHA256, 600k 迭代）。
"""
from db.base_service import BaseService
from models.base.person import Person
from utils.error_handler import logger, ServiceResult
from utils.password_utils import hash_password, verify_password, is_password_hash_set
from config.settings import DEFAULT_INITIAL_PASSWORD
from typing import List, Optional, Tuple


class PersonService(BaseService):
    """人员信息表服务

    继承BaseService，提供人员信息数据的增删改查操作。
    """

    def __init__(self, db=None):
        super().__init__("person", db=db)
        logger.info("人员服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[Person]:
        """通过记录ID查询人员"""
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_name(self, name: str) -> Optional[Person]:
        """通过姓名查询人员"""
        record = super().get_by_field('name', name)
        if record:
            return self._parse_record(record)
        return None

    def get_by_role(self, role: str) -> List[Person]:
        """通过角色查询人员"""
        records = super().get_all_by_field('role', role)
        return [self._parse_record(record) for record in records]

    def get_all_persons(self) -> List[Person]:
        """获取所有人员列表"""
        records = self.get_all()
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> Person:
        """将数据库记录解析为Person对象（Pydantic 自动校验）"""
        return Person(**record)

    # ------------------------------------------------------------------
    # 密码认证相关方法
    # ------------------------------------------------------------------

    def set_password(self, user_name: str, password: str) -> ServiceResult[bool]:
        """为用户设置密码

        Args:
            user_name: 用户名
            password: 明文密码

        Returns:
            ServiceResult[bool] - 成功返回 True
        """
        if not password or len(password) < 6:
            return ServiceResult.fail(
                message="密码长度不能少于6位",
                error_code="WEAK_PASSWORD",
            )

        person = self.get_by_name(user_name)
        if not person:
            return ServiceResult.fail(
                message=f"用户 {user_name} 不存在",
                error_code="USER_NOT_FOUND",
            )

        password_hash = hash_password(password)
        success = self.update_by_field("name", user_name, {"password_hash": password_hash})
        if success:
            logger.info(f"用户 {user_name} 密码已设置")
            return ServiceResult.ok(data=True, message="密码设置成功")
        return ServiceResult.fail(
            message="密码设置失败",
            error_code="PASSWORD_UPDATE_FAILED",
        )

    def authenticate(self, user_name: str, password: str) -> ServiceResult[Person]:
        """验证用户登录凭据

        兼容迁移期老账户：若该用户尚未设置密码（password_hash 为空），
        允许使用系统默认初始密码完成首次登录，并即时落库密码哈希。

        Args:
            user_name: 用户名
            password: 明文密码

        Returns:
            ServiceResult[Person] - 成功返回 Person 对象
        """
        person = self.get_by_name(user_name)
        if not person:
            return ServiceResult.fail(
                message="用户名或密码错误",
                error_code="AUTH_FAILED",
            )

        # 未设置密码（迁移期老账户）：仅当输入等于默认初始密码时放行
        if not is_password_hash_set(person.password_hash or ""):
            if password and password == DEFAULT_INITIAL_PASSWORD:
                new_hash = hash_password(password)
                self.update_by_field("name", user_name, {"password_hash": new_hash})
                person.password_hash = new_hash
                logger.info(f"用户 {user_name} 首次登录，已设置初始密码")
                return ServiceResult.ok(data=person, message="首次登录成功")
            return ServiceResult.fail(
                message="用户名或密码错误",
                error_code="AUTH_FAILED",
            )

        if not verify_password(password, person.password_hash):
            return ServiceResult.fail(
                message="用户名或密码错误",
                error_code="AUTH_FAILED",
            )

        logger.info(f"用户 {user_name} 登录验证成功")
        return ServiceResult.ok(data=person, message="验证通过")

    def has_password(self, user_name: str) -> bool:
        """检查用户是否已设置密码"""
        person = self.get_by_name(user_name)
        if not person:
            return False
        return is_password_hash_set(person.password_hash or "")


# 全局实例
person_service = PersonService()
