"""调配单数据服务类

对应数据表：
- allocation_order       调配单
- allocation_order_item  调配单明细
"""
from typing import List, Optional

from db.base_service import BaseService
from models.core.allocation_order import AllocationOrder, AllocationOrderItem
from utils.error_handler import logger


class AllocationOrderService(BaseService):
    """调配单服务"""

    def __init__(self):
        super().__init__("allocation_order")
        logger.info("调配单服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[AllocationOrder]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_by_number(self, allocation_number: str) -> Optional[AllocationOrder]:
        record = super().get_by_field("allocation_number", allocation_number)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[AllocationOrder]:
        return [self._parse_record(r) for r in self.get_all(order_by="id DESC")]

    def get_by_demand(self, demand_id: int) -> List[AllocationOrder]:
        records = super().get_all_by_field("demand_id", demand_id, order_by="id")
        return [self._parse_record(r) for r in records]

    def get_by_manager(self, manager: str) -> List[AllocationOrder]:
        records = super().get_all_by_field("manager", manager, order_by="id DESC")
        return [self._parse_record(r) for r in records]

    def get_pending_by_manager(self, manager: str) -> List[AllocationOrder]:
        """某管理人待处理的调配单"""
        records = self.db.execute_query(
            "SELECT * FROM allocation_order WHERE manager = ? AND status = ? ORDER BY id",
            (manager, "待处理")
        )
        return [self._parse_record(r) for r in records]

    def _parse_record(self, record: dict) -> AllocationOrder:
        return AllocationOrder(
            id=record.get('id'),
            allocation_number=record.get('allocation_number'),
            demand_id=record.get('demand_id'),
            manager=record.get('manager'),
            status=record.get('status'),
            demand_qty=record.get('demand_qty'),
            manager_stock_qty=record.get('manager_stock_qty'),
            total_stock_qty=record.get('total_stock_qty'),
            year_demand_qty=record.get('year_demand_qty'),
            is_stock_sufficient=record.get('is_stock_sufficient'),
            handled_at=record.get('handled_at'),
            remark=record.get('remark'),
            created_by=record.get('created_by'),
            created_at=record.get('created_at'),
        )


class AllocationOrderItemService(BaseService):
    """调配单明细服务"""

    def __init__(self):
        super().__init__("allocation_order_item")
        logger.info("调配单明细服务初始化完成")

    def get_by_allocation(self, allocation_id: int) -> List[AllocationOrderItem]:
        records = self.db.execute_query(
            "SELECT * FROM allocation_order_item WHERE allocation_id = ? ORDER BY id",
            (allocation_id,)
        )
        return [self._parse_record(r) for r in records]

    def _parse_record(self, record: dict) -> AllocationOrderItem:
        return AllocationOrderItem(
            id=record.get('id'),
            allocation_id=record.get('allocation_id'),
            bottle_number=record.get('bottle_number'),
            reagent_name=record.get('reagent_name'),
            qty=record.get('qty'),
            status=record.get('status'),
        )


# 全局实例
allocation_order_service = AllocationOrderService()
allocation_order_item_service = AllocationOrderItemService()
