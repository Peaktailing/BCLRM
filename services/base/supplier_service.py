"""供应商服务类

对应数据表：试剂供应商表 (supplier)

提供供应商信息的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.base.supplier import Supplier
from utils.error_handler import logger
from typing import List, Optional


class SupplierService(BaseService):
    """供应商表服务

    继承BaseService，提供供应商数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("supplier")
        logger.info("供应商服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[Supplier]:
        """通过记录ID查询供应商

        Args:
            record_id: 记录ID

        Returns:
            Supplier对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_name(self, name: str) -> Optional[Supplier]:
        """通过名称查询供应商

        Args:
            name: 供应商名称

        Returns:
            Supplier对象或None
        """
        record = super().get_by_field('name', name)
        if record:
            return self._parse_record(record)
        return None

    def get_all_suppliers(self) -> List[Supplier]:
        """获取所有供应商列表

        Returns:
            Supplier对象列表
        """
        records = self.get_all()
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> Supplier:
        """将数据库记录解析为Supplier对象

        Args:
            record: 数据库记录字典

        Returns:
            Supplier对象
        """
        return Supplier(
            id=record.get('id'),
            name=record.get('name'),
            contact=record.get('contact'),
            phone=record.get('phone'),
            address=record.get('address')
        )


# 全局实例
supplier_service = SupplierService()
