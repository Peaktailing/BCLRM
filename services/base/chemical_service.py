"""化学品信息服务类

对应数据表：化学品信息表 (chemical_info)

提供化学品信息的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.base.chemical import ChemicalInfo
from utils.error_handler import logger
from typing import List, Optional


class ChemicalService(BaseService):
    """化学品信息表服务

    继承BaseService，提供化学品信息数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("chemical_info")
        logger.info("化学品服务初始化完成")
    def get_by_id(self, record_id: int) -> Optional[ChemicalInfo]:
        """通过记录ID查询化学品信息

        Args:
            record_id: 记录ID

        Returns:
            ChemicalInfo对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_name(self, name: str) -> Optional[ChemicalInfo]:
        """通过化学品名称查询（同时匹配name和display_name）

        Args:
            name: 化学品名称

        Returns:
            ChemicalInfo对象或None
        """
        records = self.get_all_parsed()

        # 预处理：去除所有空格用于模糊匹配
        name_no_space = name.replace(" ", "") if name else ""

        for chemical in records:
            # 精确匹配化学品名称
            if chemical.name == name:
                return chemical
            # 同时匹配通用显示名称
            if chemical.display_name == name:
                return chemical
            # 支持strip后的匹配（处理首尾空格问题）
            if chemical.name and chemical.name.strip() == name.strip():
                return chemical
            if chemical.display_name and chemical.display_name.strip() == name.strip():
                return chemical
            # 支持忽略所有空格的匹配（处理中间空格问题）
            if chemical.name and chemical.name.replace(" ", "") == name_no_space:
                return chemical
            if chemical.display_name and chemical.display_name.replace(" ", "") == name_no_space:
                return chemical
        return None

    def get_by_cas(self, cas: str) -> Optional[ChemicalInfo]:
        """通过CAS号查询

        Args:
            cas: CAS号

        Returns:
            ChemicalInfo对象或None
        """
        # 使用 BaseService 的 get_by_field 方法
        record = super().get_by_field('cas', cas)
        if record:
            return self._parse_record(record)
        return None

    def get_all_parsed(self) -> List[ChemicalInfo]:
        """获取所有化学品信息（解析为ChemicalInfo对象列表）

        Returns:
            ChemicalInfo对象列表
        """
        logger.debug("正在调用get_all_parsed()")
        records = self.get_all()
        logger.debug(f"get_all() 返回 {len(records)} 条记录")

        parsed_list = []
        for record in records:
            parsed = self._parse_record(record)
            parsed_list.append(parsed)

        logger.debug(f"get_all_parsed() 完成，共解析 {len(parsed_list)} 个对象")
        return parsed_list

    def _parse_record(self, record: dict) -> ChemicalInfo:
        """将数据库记录解析为ChemicalInfo对象

        Args:
            record: 数据库记录字典

        Returns:
            ChemicalInfo对象
        """
        return ChemicalInfo(
            id=record.get('id'),
            name=record.get('name'),
            display_name=record.get('display_name'),
            formula=record.get('formula'),
            cas=record.get('cas'),
            msds=record.get('msds'),
            reagent_type=record.get('reagent_type'),
            storage_requirement=record.get('storage_requirement'),
            controlled_type=record.get('controlled_type')
        )


# 全局实例
chemical_service = ChemicalService()
