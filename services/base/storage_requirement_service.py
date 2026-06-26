"""存储要求服务类

对应数据表：存储要求表 (storage_requirement)

提供存储要求的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.base.storage_requirement import StorageRequirement
from utils.error_handler import logger
from typing import List, Optional


class StorageRequirementService(BaseService):
    """存储要求表服务

    继承BaseService，提供存储要求数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("storage_requirement")
        logger.info("存储要求服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[StorageRequirement]:
        """通过记录ID查询存储要求

        Args:
            record_id: 记录ID

        Returns:
            StorageRequirement对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_name(self, name: str) -> Optional[StorageRequirement]:
        """通过名称查询存储要求

        Args:
            name: 存储要求名称

        Returns:
            StorageRequirement对象或None
        """
        record = super().get_by_field('name', name)
        if record:
            return self._parse_record(record)
        return None

    def get_all_requirements(self) -> List[StorageRequirement]:
        """获取所有存储要求（解析为StorageRequirement对象列表）

        Returns:
            StorageRequirement对象列表
        """
        logger.debug("正在调用get_all_requirements()")
        records = self.get_all()

        parsed_list = []
        for record in records:
            parsed = self._parse_record(record)
            parsed_list.append(parsed)

        logger.debug(f"get_all_requirements() 完成，共解析 {len(parsed_list)} 个对象")
        return parsed_list

    def get_all_names(self) -> List[str]:
        """获取所有存储要求的名称列表（用于下拉框）

        Returns:
            名称列表
        """
        records = self.get_all()
        return [
            record.get('name', "")
            for record in records
            if record.get('name')
        ]

    def _parse_record(self, record: dict) -> StorageRequirement:
        """将数据库记录解析为StorageRequirement对象

        Args:
            record: 数据库记录字典

        Returns:
            StorageRequirement对象
        """
        return StorageRequirement(
            id=record.get('id'),
            name=record.get('name'),
            description=record.get('description')
        )


# 全局实例
storage_requirement_service = StorageRequirementService()
