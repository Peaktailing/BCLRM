"""调拨单数据模型（字段形状；状态常量在 ``domain/transfer.py``）

与 ``allocation_order`` 的区别——两者都叫「调配」，但答的是不同问题：

- ``allocation_order``：「这个人名下够不够发」→ 智能分配算完了，发一张单
  通知他；单上没有出料人，也没有对方点头。
- ``transfer_order``（本文件）：「这批货从谁名下转到谁名下」→ 保管权真的
  换人，所以有出料人、有受益人、有谁点的头。

一张单 = 一个出料人 → 一个受益人。三个出料人就三张单：点头这个动作是
「我把我名下这几瓶转给他」，合成一张会出现「甲同意了、乙还没看」的中间态。
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TransferOrder:
    """调拨单（保管权流转）"""
    id: Optional[int] = None
    transfer_number: Optional[str] = None
    from_manager: Optional[str] = None
    to_manager: Optional[str] = None
    reason: Optional[str] = None
    origin_kind: Optional[str] = None
    origin_ref: Optional[str] = None
    status: Optional[str] = None
    requested_by: Optional[str] = None
    requested_at: Optional[str] = None
    respondent: Optional[str] = None
    answered_at: Optional[str] = None
    answer_remark: Optional[str] = None
    executed_at: Optional[str] = None
    forced: Optional[int] = 0
    picked_up_at: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[str] = None
    #: 明细由服务层按需装载，不参与建单
    items: List["TransferOrderItem"] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        from domain.transfer import TRANSFER_OPEN_STATUSES

        return (self.status or "").strip() in TRANSFER_OPEN_STATUSES


@dataclass
class TransferOrderItem:
    """调拨单明细（一行 = 一瓶）"""
    id: Optional[int] = None
    transfer_id: Optional[int] = None
    line_no: Optional[int] = None
    lot_id: Optional[str] = None
    substance_key: Optional[str] = None
    cas_number: Optional[str] = None
    display_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    line_status: Optional[str] = None
    note: Optional[str] = None

    @property
    def label(self) -> str:
        name = self.display_name or self.substance_key or ""
        qty = f"{self.quantity:g}" if self.quantity is not None else ""
        unit = self.unit or ""
        lot = f"（{self.lot_id}）" if self.lot_id else "（现场指定）"
        return f"{name} {qty} {unit}{lot}".strip()
