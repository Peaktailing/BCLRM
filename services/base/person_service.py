"""人员服务类

对应数据表：人员信息表 (person)

提供人员信息的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.base.person import Person
from utils.error_handler import logger, ServiceResult
from utils.password_utils import hash_password, verify_password, is_password_hash_set
from typing import List, Optional, Tuple


class PersonService(BaseService):
    """人员信息表服务

    继承BaseService，提供人员信息数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("person")
        logger.info("人员服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[Person]:
        """通过记录ID查询人员

        Args:
            record_id: 记录ID

        Returns:
            Person对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_name(self, name: str) -> Optional[Person]:
        """通过姓名查询人员

        Args:
            name: 人员姓名

        Returns:
            Person对象或None
        """
        record = super().get_by_field('name', name)
        if record:
            return self._parse_record(record)
        return None

    def get_by_role(self, role: str) -> List[Person]:
        """通过角色查询人员

        Args:
            role: 人员角色

        Returns:
            Person对象列表
        """
        records = super().get_all_by_field('role', role)
        return [self._parse_record(record) for record in records]

    def get_all_persons(self) -> List[Person]:
        """获取所有人员列表

        Returns:
            Person对象列表
        """
        records = self.get_all()
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> Person:
        """将数据库记录解析为Person对象

        Args:
            record: 数据库记录字典

        Returns:
            Person对象
        """
        return Person(
            id=record.get('id'),
            name=record.get('name'),
            role=record.get('role'),
            department=record.get('department'),
            phone=record.get('phone'),
            student_or_work_id=record.get('student_or_work_id'),
            password_hash=record.get('password_hash'),
        )

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

        Args:
            user_name: 用户名
            password: 明文密码

        Returns:
            ServiceResult[Person] - 成功返回 Person 对象
        """
        person = self.get_by_name(user_name)
        if not person:
            return ServiceResult.fail(
                message="用户名不存在",
                error_code="USER_NOT_FOUND",
            )

        # 如果用户未设置密码，拒绝登录
        if not is_password_hash_set(person.password_hash or ""):
            return ServiceResult.fail(
                message="该用户尚未设置密码，请联系管理员",
                error_code="PASSWORD_NOT_SET",
            )

        if not verify_password(password, person.password_hash):
            return ServiceResult.fail(
                message="密码错误",
                error_code="WRONG_PASSWORD",
            )

        logger.info(f"用户 {user_name} 登录验证成功")
        return ServiceResult.ok(data=person, message="验证通过")

    def has_password(self, user_name: str) -> bool:
        """检查用户是否已设置密码

        Args:
            user_name: 用户名

        Returns:
            True 表示已设置密码
        """
        person = self.get_by_name(user_name)
        if not person:
            return False
        return is_password_hash_set(person.password_hash or "")


# 全局实例
person_service = PersonService()
