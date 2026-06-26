"""存储位置服务类

对应数据表：存储位置表 (storage_location)

提供存储位置的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.base.storage_location import StorageLocation
from utils.error_handler import logger
from typing import List, Optional


class StorageLocationService(BaseService):
    """存储位置表服务

    继承BaseService，提供存储位置数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("storage_location")
        logger.info("存储位置服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[StorageLocation]:
        """通过记录ID查询存储位置

        Args:
            record_id: 记录ID

        Returns:
            StorageLocation对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_name(self, name: str) -> Optional[StorageLocation]:
        """通过名称查询存储位置

        Args:
            name: 存储位置名称

        Returns:
            StorageLocation对象或None
        """
        record = super().get_by_field('name', name)
        if record:
            return self._parse_record(record)
        return None

    def get_all_locations(self) -> List[StorageLocation]:
        """获取所有存储位置

        Returns:
            StorageLocation对象列表
        """
        records = self.get_all()
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> StorageLocation:
        """将数据库记录解析为StorageLocation对象

        Args:
            record: 数据库记录字典

        Returns:
            StorageLocation对象
        """
        return StorageLocation(
            id=record.get('id'),
            name=record.get('name'),
            description=record.get('description')
        )


# 全局实例
storage_location_service = StorageLocationService()
