"""预定单与采购单数据模型

- reservation_order  预定单（库存不足时提前预定，审批后转采购）
- purchase_order     采购单（正式下单采购，状态流转到到货）
"""
from dataclasses import dataclass
from typing import Optional

# 预定单状态
RESERVATION_PENDING = "pending"      # 待审批
RESERVATION_APPROVED = "approved"    # 已批准
RESERVATION_REJECTED = "rejected"    # 已驳回
RESERVATION_FULFILLED = "fulfilled"  # 已满足（到货）

RESERVATION_STATUS_LABELS = {
    RESERVATION_PENDING: "待审批",
    RESERVATION_APPROVED: "已批准",
    RESERVATION_REJECTED: "已驳回",
    RESERVATION_FULFILLED: "已满足",
}

# 采购单状态
PO_PENDING = "pending"      # 待下单
PO_ORDERED = "ordered"      # 已下单
PO_RECEIVED = "received"    # 已到货
PO_CANCELLED = "cancelled"  # 已取消

PO_STATUS_LABELS = {
    PO_PENDING: "待下单",
    PO_ORDERED: "已下单",
    PO_RECEIVED: "已到货",
    PO_CANCELLED: "已取消",
}


@dataclass
class ReservationOrder:
    """预定单"""
    id: Optional[int] = None
    order_number: Optional[str] = None   # 单号（RES + 时间戳）
    semester: Optional[str] = None       # 需求学年
    reagent_name: Optional[str] = None
    cas_number: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    applicant: Optional[str] = None
    status: Optional[str] = None


@dataclass
class PurchaseOrder:
    """采购单（单试剂一单）"""
    id: Optional[int] = None
    order_number: Optional[str] = None   # 单号（PO + 时间戳）
    reservation_order_id: Optional[int] = None  # 来源预定单（可空）
    reagent_name: Optional[str] = None
    cas_number: Optional[str] = None
    order_quantity: Optional[float] = None
    unit_price: Optional[float] = None
    supplier: Optional[str] = None
    status: Optional[str] = None
