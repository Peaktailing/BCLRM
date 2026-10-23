"""库存快照装配：从 ``reagent_bottle`` 读一份只读快照。

业务层与中台都不直接读库存表——它们要的是一份 ``StockSnapshot``。
这个模块是唯一的转换点，也是「库存表结构变了要改哪里」的答案。

读全表而非按物质过滤，是因为一次计算通常要覆盖十几个物质，逐物质
查询反而更慢（且会造成同一张单的不同行走在不同时点的库存上）。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from capabilities.supply import StockSnapshot
from utils.error_handler import logger

#: 只取计算需要的列，避免整行搬运
_COLUMNS = (
    "bottle_number",
    "reagent_name",
    "cas_number",
    "remaining_quantity",
    "specification",
    "unit",
    "is_controlled",
    "storage_location",
    "borrowable_flag",
    "borrowable_check",
    "expired_flag",
    "expiry_date",
    "scrap_flag",
    "unit_price",
)


class BottleStockProvider:
    """试剂瓶库存快照来源。"""

    def __init__(self, service=None) -> None:
        self._service = service

    @property
    def service(self):
        if self._service is None:
            from services.core.reagent_bottle_service import reagent_bottle_service
            self._service = reagent_bottle_service
        return self._service

    def snapshot(self, label: str = "") -> StockSnapshot:
        try:
            rows = self.service.get_all(order_by="reagent_name")
        except Exception as exc:
            logger.error(f"库存快照读取失败，按空库存处理: {exc}", exception=exc)
            rows = []
        return StockSnapshot.from_bottle_rows(rows, label=label)

    def snapshot_rows(self, rows: Iterable[Mapping[str, Any]], label: str = "") -> StockSnapshot:
        """从外部给的行构造（测试与批量导入用）。"""
        return StockSnapshot.from_bottle_rows(rows, label=label)


def snapshot_from_rows(rows: Iterable[Mapping[str, Any]], label: str = "") -> StockSnapshot:
    return StockSnapshot.from_bottle_rows(rows, label=label)


__all__ = ["BottleStockProvider", "snapshot_from_rows", "_COLUMNS"]
