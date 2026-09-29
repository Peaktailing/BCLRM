"""调配单数据模型

对应 SQLite 表：
- allocation_order       调配单（按管理人拆分，发到对应管理人手上）
- allocation_order_item  调配单明细（每瓶试剂一条）

调配单受理人 = 该批试剂瓶当前管理人。管理员决定「借出 / 退回」：
- 借出：走正常领用（借出/归还操作不变，**不改变管理人**）；
- 退回：驳回该调配单。
"""
from dataclasses import dataclass
from typing import Optional

# 调配单状态
ALLOC_STATUS_PENDING = "待处理"
ALLOC_STATUS_LENT = "已借出"
ALLOC_STATUS_REJECTED = "已退回"

# 明细状态
ALLOC_ITEM_PENDING = "待处理"
ALLOC_ITEM_LENT = "已借出"
ALLOC_ITEM_REJECTED = "已退回"


@dataclass
class AllocationOrder:
    """调配单"""
    id: Optional[int] = None
    allocation_number: Optional[str] = None
    demand_id: Optional[int] = None
    manager: Optional[str] = None
    status: Optional[str] = None
    demand_qty: Optional[float] = None
    manager_stock_qty: Optional[float] = None
    total_stock_qty: Optional[float] = None
    year_demand_qty: Optional[float] = None
    is_stock_sufficient: Optional[int] = None
    handled_at: Optional[str] = None
    remark: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class AllocationOrderItem:
    """调配单明细"""
    id: Optional[int] = None
    allocation_id: Optional[int] = None
    bottle_number: Optional[str] = None
    reagent_name: Optional[str] = None
    qty: Optional[float] = None
    status: Optional[str] = None
