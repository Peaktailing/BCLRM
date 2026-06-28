"""管控化学品名录服务类

对应数据表：管控化学品名录 (controlled_list)

提供管控化学品名录的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.base.controlled_list import ControlledList
from utils.error_handler import logger
from typing import List, Optional


class ControlledListService(BaseService):
    """管控化学品名录表服务

    继承BaseService，提供管控化学品名录数据的增删改查操作。
    主要用于领用审批时判断试剂是否为管控试剂。
    """

    def __init__(self):
        super().__init__("controlled_list")
        logger.info("管控化学品名录服务初始化完成")
    def get_by_id(self, record_id: int) -> Optional[ControlledList]:
        """通过记录ID查询管控化学品

        Args:
            record_id: 记录ID

        Returns:
            ControlledList对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_cas_number(self, cas_number: str) -> Optional[ControlledList]:
        """通过CAS号查询管控化学品

        Args:
            cas_number: CAS号

        Returns:
            ControlledList对象或None
        """
        record = super().get_by_field('cas_number', cas_number)
        if record:
            return self._parse_record(record)
        return None

    def get_by_name(self, chemical_name: str) -> Optional[ControlledList]:
        """通过化学品名称查询

        Args:
            chemical_name: 化学品名称

        Returns:
            ControlledList对象或None
        """
        record = super().get_by_field('chemical_name', chemical_name)
        if record:
            return self._parse_record(record)
        return None

    def is_controlled(self, cas_number: str) -> bool:
        """检查CAS号是否在管控名录中

        Args:
            cas_number: CAS号

        Returns:
            是否为管控化学品
        """
        return self.get_by_cas_number(cas_number) is not None

    def get_all_controlled(self) -> List[ControlledList]:
        """获取所有管控化学品

        Returns:
            ControlledList对象列表
        """
        records = self.get_all()
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> ControlledList:
        """将数据库记录解析为ControlledList对象

        Args:
            record: 数据库记录字典

        Returns:
            ControlledList对象
        """
        return ControlledList(
            id=record.get('id'),
            chemical_name=record.get('chemical_name'),
            alias=record.get('alias'),
            cas_number=record.get('cas_number'),
            dangerous_type=record.get('dangerous_type')
        )


# 全局实例
controlled_list_service = ControlledListService()
