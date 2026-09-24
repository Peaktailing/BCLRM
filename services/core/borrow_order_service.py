"""领用工单数据服务类

对应数据表：
- borrow_order        领用工单
- borrow_order_item   工单明细
"""
from typing import List, Optional

from db.base_service import BaseService
from models.core.borrow_order import BorrowOrder, BorrowOrderItem
from utils.error_handler import logger


class BorrowOrderService(BaseService):
    """领用工单服务"""

    def __init__(self):
        super().__init__("borrow_order")
        logger.info("领用工单服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[BorrowOrder]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[BorrowOrder]:
        """全部工单（最新在前）"""
        return [self._parse_record(record) for record in self.get_all(order_by="id DESC")]

    def get_by_order_number(self, order_number: str) -> Optional[BorrowOrder]:
        record = super().get_by_field("order_number", order_number)
        return self._parse_record(record) if record else None

    def _parse_record(self, record: dict) -> BorrowOrder:
        return BorrowOrder(
            id=record.get('id'),
            order_number=record.get('order_number'),
            order_type=record.get('order_type'),
            applicant=record.get('applicant'),
            borrow_time=record.get('borrow_time'),
            course_id=record.get('course_id'),
            item_id=record.get('item_id'),
            course_name=record.get('course_name'),
            item_name=record.get('item_name'),
            status=record.get('status'),
            remark=record.get('remark'),
            created_by=record.get('created_by'),
        )


class BorrowOrderItemService(BaseService):
    """领用工单明细服务"""

    def __init__(self):
        super().__init__("borrow_order_item")
        logger.info("领用工单明细服务初始化完成")

    def get_by_order(self, order_id: int) -> List[BorrowOrderItem]:
        records = self.db.execute_query(
            "SELECT * FROM borrow_order_item WHERE order_id = ? ORDER BY id",
            (order_id,)
        )
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> BorrowOrderItem:
        return BorrowOrderItem(
            id=record.get('id'),
            order_id=record.get('order_id'),
            bottle_number=record.get('bottle_number'),
            reagent_name=record.get('reagent_name'),
            borrow_qty=record.get('borrow_qty'),
            returned_qty=record.get('returned_qty'),
            status=record.get('status'),
        )


# 全局实例
borrow_order_service = BorrowOrderService()
borrow_order_item_service = BorrowOrderItemService()
