"""需求单数据模型

对应 SQLite 表：
- reagent_demand       需求单（领用需求）
- reagent_demand_item  需求单明细（只记「要什么、多少」，不与试剂瓶绑定）

需求提交后，由智能分配按「管理人」拆分为若干调配单。
"""
from dataclasses import dataclass
from typing import Optional

# 需求单状态
DEMAND_STATUS_PENDING = "待调配"     # 已提交，存在未处理的调配单
DEMAND_STATUS_DONE = "已完成"        # 所有调配单均已借出
DEMAND_STATUS_PARTIAL = "部分完成"    # 部分调配单借出、部分退回
DEMAND_STATUS_REJECTED = "已驳回"     # 所有调配单均被退回
DEMAND_STATUS_CANCELLED = "已撤销"    # 需求人主动撤销（无已借出的调配单）


@dataclass
class ReagentDemand:
    """需求单"""
    id: Optional[int] = None
    demand_number: Optional[str] = None
    requester: Optional[str] = None
    order_type: Optional[str] = None
    course_id: Optional[int] = None
    item_id: Optional[int] = None
    project_id: Optional[int] = None
    course_name: Optional[str] = None
    item_name: Optional[str] = None
    borrow_time: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class ReagentDemandItem:
    """需求单明细"""
    id: Optional[int] = None
    demand_id: Optional[int] = None
    reagent_name: Optional[str] = None
    cas_number: Optional[str] = None
    requested_qty: Optional[float] = None
