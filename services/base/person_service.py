"""人员服务类

对应数据表：人员信息表 (person)

提供人员信息的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.base.person import Person
from utils.error_handler import logger
from utils.password_utils import hash_password, verify_password
from typing import List, Optional


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

    def create_with_password(self, name: str, password: str, role: str = "user",
                             department: str = None, phone: str = None,
                             student_or_work_id: str = None) -> Optional[int]:
        """创建带密码的用户

        Args:
            name: 用户名
            password: 明文密码
            role: 用户角色
            department: 部门
            phone: 电话
            student_or_work_id: 学号/工号

        Returns:
            新记录的ID，失败返回None
        """
        password_h = hash_password(password)
        fields = {
            "name": name,
            "password_hash": password_h,
            "role": role
        }
        if department:
            fields["department"] = department
        if phone:
            fields["phone"] = phone
        if student_or_work_id:
            fields["student_or_work_id"] = student_or_work_id

        return self.create(fields)

    def verify_user_password(self, name: str, password: str) -> bool:
        """验证用户密码

        Args:
            name: 用户名
            password: 明文密码

        Returns:
            True 表示验证通过
        """
        person = self.get_by_name(name)
        if not person:
            return False
        if not person.password_hash:
            return False
        return verify_password(password, person.password_hash)

    def update_password(self, name: str, new_password: str) -> bool:
        """更新用户密码

        Args:
            name: 用户名
            new_password: 新密码

        Returns:
            True 表示更新成功
        """
        person = self.get_by_name(name)
        if not person:
            return False
        password_h = hash_password(new_password)
        return self.update(person.id, {"password_hash": password_h})

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
            password_hash=record.get('password_hash')
        )


# 全局实例
person_service = PersonService()
