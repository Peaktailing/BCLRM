"""领用工单数据模型

- borrow_order       领用工单（零星领用 / 课程领用）
- borrow_order_item  工单明细（每瓶试剂一条，记录领用量与已归还量）
"""
from dataclasses import dataclass
from typing import Optional

# 工单类型
ORDER_TYPE_SPORADIC = "零星领用"
ORDER_TYPE_COURSE = "课程领用"

# 工单状态
ORDER_STATUS_BORROWING = "借用中"
ORDER_STATUS_PARTIAL = "部分归还"
ORDER_STATUS_RETURNED = "已归还"

# 明细状态
ITEM_STATUS_PENDING = "待归还"
ITEM_STATUS_RETURNED = "已归还"


@dataclass
class BorrowOrder:
    """领用工单"""
    id: Optional[int] = None
    order_number: Optional[str] = None
    order_type: Optional[str] = None      # 零星领用 / 课程领用
    applicant: Optional[str] = None       # 领用人
    borrow_time: Optional[str] = None     # 领用时间（用于学期归属）
    course_id: Optional[int] = None
    item_id: Optional[int] = None         # 实验项目
    course_name: Optional[str] = None     # 课程名快照
    item_name: Optional[str] = None       # 实验名快照
    status: Optional[str] = None          # 借用中 / 部分归还 / 已归还
    remark: Optional[str] = None
    created_by: Optional[str] = None


@dataclass
class BorrowOrderItem:
    """领用工单明细"""
    id: Optional[int] = None
    order_id: Optional[int] = None
    bottle_number: Optional[str] = None
    reagent_name: Optional[str] = None
    borrow_qty: Optional[float] = None      # 领用量
    returned_qty: Optional[float] = None    # 已归还量
    status: Optional[str] = None            # 待归还 / 已归还
