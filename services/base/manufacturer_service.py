"""生产商服务类

对应数据表：试剂生产商表 (manufacturer)

提供生产商信息的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.base.manufacturer import Manufacturer
from utils.error_handler import logger
from typing import List, Optional


class ManufacturerService(BaseService):
    """生产商表服务

    继承BaseService，提供生产商数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("manufacturer")
        logger.info("生产商服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[Manufacturer]:
        """通过记录ID查询生产商

        Args:
            record_id: 记录ID

        Returns:
            Manufacturer对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_name(self, name: str) -> Optional[Manufacturer]:
        """通过名称查询生产商

        Args:
            name: 生产商名称

        Returns:
            Manufacturer对象或None
        """
        record = super().get_by_field('name', name)
        if record:
            return self._parse_record(record)
        return None

    def get_all_manufacturers(self) -> List[Manufacturer]:
        """获取所有生产商列表

        Returns:
            Manufacturer对象列表
        """
        records = self.get_all()
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> Manufacturer:
        """将数据库记录解析为Manufacturer对象

        Args:
            record: 数据库记录字典

        Returns:
            Manufacturer对象
        """
        return Manufacturer(
            id=record.get('id'),
            name=record.get('name'),
            contact=record.get('contact'),
            phone=record.get('phone'),
            address=record.get('address')
        )


# 全局实例
manufacturer_service = ManufacturerService()
