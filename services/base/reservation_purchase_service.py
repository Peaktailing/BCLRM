"""预定单与采购单服务类

对应数据表：
- reservation_order  预定单（pending → approved/rejected → fulfilled）
- purchase_order     采购单（pending → ordered → received / cancelled）
"""
from typing import List, Optional

from db.base_service import BaseService
from models.base.purchase_order import (
    PO_PENDING,
    PO_STATUS_LABELS,
    RESERVATION_PENDING,
    RESERVATION_STATUS_LABELS,
    PurchaseOrder,
    ReservationOrder,
)
from utils.error_handler import logger


class ReservationOrderService(BaseService):
    """预定单服务"""

    def __init__(self):
        super().__init__("reservation_order")
        logger.info("预定单服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ReservationOrder]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[ReservationOrder]:
        return [self._parse_record(r) for r in self.get_all(order_by="id DESC")]

    def get_by_status(self, status: str) -> List[ReservationOrder]:
        return [
            self._parse_record(r)
            for r in super().get_all_by_field("status", status)
        ]

    @staticmethod
    def status_label(status: Optional[str]) -> str:
        return RESERVATION_STATUS_LABELS.get(status or "", status or "-")

    def _parse_record(self, record: dict) -> ReservationOrder:
        return ReservationOrder(
            id=record.get("id"),
            order_number=record.get("order_number"),
            semester=record.get("semester"),
            reagent_name=record.get("reagent_name"),
            cas_number=record.get("cas_number"),
            quantity=record.get("quantity"),
            unit=record.get("unit"),
            applicant=record.get("applicant"),
            status=record.get("status"),
        )


class PurchaseOrderService(BaseService):
    """采购单服务"""

    def __init__(self):
        super().__init__("purchase_order")
        logger.info("采购单服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[PurchaseOrder]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[PurchaseOrder]:
        return [self._parse_record(r) for r in self.get_all(order_by="id DESC")]

    def get_by_status(self, status: str) -> List[PurchaseOrder]:
        return [self._parse_record(r) for r in super().get_all_by_field("status", status)]

    @staticmethod
    def status_label(status: Optional[str]) -> str:
        return PO_STATUS_LABELS.get(status or "", status or "-")

    def _parse_record(self, record: dict) -> PurchaseOrder:
        return PurchaseOrder(
            id=record.get("id"),
            order_number=record.get("order_number"),
            reservation_order_id=record.get("reservation_order_id"),
            reagent_name=record.get("reagent_name"),
            cas_number=record.get("cas_number"),
            order_quantity=record.get("order_quantity"),
            unit_price=record.get("unit_price"),
            supplier=record.get("supplier"),
            status=record.get("status"),
        )


# 全局实例
reservation_order_service = ReservationOrderService()
purchase_order_service = PurchaseOrderService()
