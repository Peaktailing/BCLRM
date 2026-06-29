"""试剂类型服务类

对应数据表：试剂类型表 (reagent_type)

提供试剂类型的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.base.reagent_type import ReagentType
from utils.error_handler import logger
from typing import List, Optional


class ReagentTypeService(BaseService):
    """试剂类型表服务

    继承BaseService，提供试剂类型数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("reagent_type")
        logger.info("试剂类型服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ReagentType]:
        """通过记录ID查询试剂类型

        Args:
            record_id: 记录ID

        Returns:
            ReagentType对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_name(self, name: str) -> Optional[ReagentType]:
        """通过名称查询试剂类型

        Args:
            name: 试剂类型名称

        Returns:
            ReagentType对象或None
        """
        record = super().get_by_field('name', name)
        if record:
            return self._parse_record(record)
        return None

    def get_all_types(self) -> List[ReagentType]:
        """获取所有试剂类型（解析为ReagentType对象列表）

        Returns:
            ReagentType对象列表
        """
        logger.debug("正在调用get_all_types()")
        records = self.get_all()

        parsed_list = []
        for record in records:
            parsed = self._parse_record(record)
            parsed_list.append(parsed)

        logger.debug(f"get_all_types() 完成，共解析 {len(parsed_list)} 个对象")
        return parsed_list

    def get_all_names(self) -> List[str]:
        """获取所有试剂类型的名称列表（用于下拉框）

        Returns:
            名称列表
        """
        records = self.get_all()
        return [
            record.get('name', "")
            for record in records
            if record.get('name')
        ]

    def _parse_record(self, record: dict) -> ReagentType:
        """将数据库记录解析为ReagentType对象

        Args:
            record: 数据库记录字典

        Returns:
            ReagentType对象
        """
        return ReagentType(
            id=record.get('id'),
            name=record.get('name'),
            description=record.get('description'),
            default_unsealed_shelf_life=record.get('default_unsealed_shelf_life'),
            default_sealed_shelf_life=record.get('default_sealed_shelf_life'),
        )


# 全局实例
reagent_type_service = ReagentTypeService()
