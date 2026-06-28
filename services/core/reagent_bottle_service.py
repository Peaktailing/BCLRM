"""试剂瓶服务类

对应数据表：试剂瓶信息表 (reagent_bottle)

提供试剂瓶的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.core.reagent_bottle import ReagentBottle
from utils.error_handler import logger
from typing import List, Optional


class ReagentBottleService(BaseService):
    """试剂瓶信息表服务

    继承BaseService，提供试剂瓶数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("reagent_bottle")
        logger.info("试剂瓶服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ReagentBottle]:
        """通过记录ID查询试剂瓶

        Args:
            record_id: 记录ID

        Returns:
            ReagentBottle对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_barcode(self, barcode: str) -> Optional[ReagentBottle]:
        """通过条码查询试剂瓶

        Args:
            barcode: 条码

        Returns:
            ReagentBottle对象或None
        """
        record = super().get_by_field('barcode', barcode)
        if record:
            return self._parse_record(record)
        return None

    def get_by_bottle_number(self, bottle_number: int) -> Optional[ReagentBottle]:
        """通过试剂瓶编号查询（主键查询）

        Args:
            bottle_number: 试剂瓶编号

        Returns:
            ReagentBottle对象或None
        """
        record = super().get_by_field('bottle_number', bottle_number)
        if record:
            return self._parse_record(record)
        return None

    def get_by_reagent_name(self, reagent_name: str) -> List[ReagentBottle]:
        """通过试剂名称查询（支持模糊匹配）

        Args:
            reagent_name: 试剂名称（支持模糊匹配）

        Returns:
            ReagentBottle对象列表
        """
        # 使用 BaseService 的 search 方法进行模糊搜索
        records = super().search(reagent_name, ['reagent_name'])
        return [self._parse_record(record) for record in records]

    def get_borrowable(self) -> List[ReagentBottle]:
        """获取所有可借的试剂瓶

        Returns:
            ReagentBottle对象列表
        """
        records = super().get_all_by_field('borrowable_flag', '可借')
        return [self._parse_record(record) for record in records]

    def search_multi_condition(
        self,
        bottle_number: Optional[int] = None,
        reagent_name: Optional[str] = None,
        cas_number: Optional[str] = None,
        supplier: Optional[str] = None,
        storage_location: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        order_by: str = None
    ) -> List[ReagentBottle]:
        """多条件数据库层查询试剂瓶（过滤在SQL层执行）

        Args:
            bottle_number: 试剂瓶编号（精确匹配）
            reagent_name: 试剂名称（模糊匹配）
            cas_number: CAS编号（精确匹配）
            supplier: 供应商（模糊匹配）
            storage_location: 存储位置（精确匹配）
            status: 状态（精确匹配，如 "可借"、"已借出"、"耗尽"）
            keyword: 关键词（跨字段模糊匹配：试剂名称、CAS号、试剂瓶编号）
            order_by: 排序字段

        Returns:
            ReagentBottle对象列表
        """
        conditions = []

        if bottle_number is not None:
            conditions.append({
                "field": "bottle_number",
                "value": bottle_number,
                "match_type": "exact"
            })

        if reagent_name:
            conditions.append({
                "field": "reagent_name",
                "value": reagent_name,
                "match_type": "fuzzy"
            })

        if cas_number:
            conditions.append({
                "field": "cas_number",
                "value": cas_number,
                "match_type": "exact"
            })

        if supplier:
            conditions.append({
                "field": "supplier",
                "value": supplier,
                "match_type": "fuzzy"
            })

        if storage_location:
            conditions.append({
                "field": "storage_location",
                "value": storage_location,
                "match_type": "exact"
            })

        if status:
            conditions.append({
                "field": "borrowable_flag",
                "value": status,
                "match_type": "exact"
            })

        if keyword:
            conditions.append({
                "field": "reagent_name",
                "value": keyword,
                "match_type": "keyword",
                "keyword_fields": ["reagent_name", "cas_number", "CAST(bottle_number AS TEXT)"]
            })

        records = super().search_multi_condition(conditions, order_by=order_by)
        return [self._parse_record(record) for record in records]

    def get_all_parsed(self) -> List[ReagentBottle]:
        """获取所有试剂瓶记录（解析为ReagentBottle对象列表）

        Returns:
            ReagentBottle对象列表
        """
        records = self.get_all()
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> ReagentBottle:
        """将数据库记录解析为ReagentBottle对象

        Args:
            record: 数据库记录字典

        Returns:
            ReagentBottle对象
        """
        return ReagentBottle(
            id=record.get('id'),
            bottle_number=record.get('bottle_number', 0),
            barcode=record.get('barcode'),
            reagent_name=record.get('reagent_name'),
            cas_number=record.get('cas_number'),
            remaining_quantity=record.get('remaining_quantity'),
            specification=record.get('specification'),
            purity=record.get('purity'),
            unit_price=record.get('unit_price'),
            supplier=record.get('supplier'),
            production_date=record.get('production_date'),
            inbound_date=record.get('inbound_date'),
            unseal_date=record.get('unseal_date'),
            last_borrow_time=record.get('last_borrow_time'),
            last_return_time=record.get('last_return_time'),
            last_return_record_no=record.get('last_return_record_no'),
            storage_location=record.get('storage_location'),
            borrowable_flag=record.get('borrowable_flag'),
            borrowable_check=record.get('borrowable_check')
        )

# 全局实例
reagent_bottle_service = ReagentBottleService()