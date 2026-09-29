"""需求单数据服务类

对应数据表：
- reagent_demand       需求单
- reagent_demand_item  需求单明细
"""
from typing import List, Optional

from db.base_service import BaseService
from models.core.reagent_demand import ReagentDemand, ReagentDemandItem
from utils.error_handler import logger


class ReagentDemandService(BaseService):
    """需求单服务"""

    def __init__(self):
        super().__init__("reagent_demand")
        logger.info("需求单服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ReagentDemand]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_by_number(self, demand_number: str) -> Optional[ReagentDemand]:
        record = super().get_by_field("demand_number", demand_number)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[ReagentDemand]:
        """全部需求单（最新在前）"""
        return [self._parse_record(r) for r in self.get_all(order_by="id DESC")]

    def get_by_requester(self, requester: str) -> List[ReagentDemand]:
        """某需求人的需求单（最新在前）"""
        records = super().get_all_by_field("requester", requester, order_by="id DESC")
        return [self._parse_record(r) for r in records]

    def _parse_record(self, record: dict) -> ReagentDemand:
        return ReagentDemand(
            id=record.get('id'),
            demand_number=record.get('demand_number'),
            requester=record.get('requester'),
            order_type=record.get('order_type'),
            course_id=record.get('course_id'),
            item_id=record.get('item_id'),
            project_id=record.get('project_id'),
            course_name=record.get('course_name'),
            item_name=record.get('item_name'),
            borrow_time=record.get('borrow_time'),
            status=record.get('status'),
            remark=record.get('remark'),
            created_by=record.get('created_by'),
            created_at=record.get('created_at'),
        )


class ReagentDemandItemService(BaseService):
    """需求单明细服务"""

    def __init__(self):
        super().__init__("reagent_demand_item")
        logger.info("需求单明细服务初始化完成")

    def get_by_demand(self, demand_id: int) -> List[ReagentDemandItem]:
        records = self.db.execute_query(
            "SELECT * FROM reagent_demand_item WHERE demand_id = ? ORDER BY id",
            (demand_id,)
        )
        return [self._parse_record(r) for r in records]

    def get_all_parsed(self) -> List[ReagentDemandItem]:
        return [self._parse_record(r) for r in self.get_all(order_by="id DESC")]

    def _parse_record(self, record: dict) -> ReagentDemandItem:
        return ReagentDemandItem(
            id=record.get('id'),
            demand_id=record.get('demand_id'),
            reagent_name=record.get('reagent_name'),
            cas_number=record.get('cas_number'),
            requested_qty=record.get('requested_qty'),
        )


# 全局实例
reagent_demand_service = ReagentDemandService()
reagent_demand_item_service = ReagentDemandItemService()
