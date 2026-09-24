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
ORDER_STATUS_PENDING = "待审批"
ORDER_STATUS_BORROWING = "借用中"
ORDER_STATUS_PARTIAL = "部分归还"
ORDER_STATUS_RETURNED = "已归还"
ORDER_STATUS_REJECTED = "已驳回"

# 审批状态
APPROVAL_NOT_REQUIRED = "无需审批"
APPROVAL_PENDING = "待审批"
APPROVAL_APPROVED = "已批准"
APPROVAL_REJECTED = "已驳回"

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
    project_id: Optional[int] = None      # 非课程类实验项目
    course_name: Optional[str] = None     # 课程名快照
    item_name: Optional[str] = None       # 实验名快照
    status: Optional[str] = None          # 待审批 / 借用中 / 部分归还 / 已归还 / 已驳回
    approval_status: Optional[str] = None  # 无需审批 / 待审批 / 已批准 / 已驳回
    approver: Optional[str] = None         # 审批人
    approval_time: Optional[str] = None    # 审批时间
    approval_remark: Optional[str] = None  # 审批意见 / 驳回原因
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
