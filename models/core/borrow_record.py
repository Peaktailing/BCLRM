"""领用记录表数据模型

对应 SQLite 表：borrow_record

字段映射说明：
- 记录编号 -> record_number (主键)
- 试剂瓶编号 -> bottle_number
- 试剂名称 -> reagent_name
- 领用人 -> user
- CAS号 -> cas_number
- 生产日期 -> production_date
- 领用时间 -> borrow_time
- 审批人 -> approver
- 审批记录上传 -> approval_file
- 是否通过审批 -> approved
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class BorrowRecord:
    """领用记录数据模型
    
    记录所有试剂领用操作，用于追踪试剂的使用历史和责任归属。
    """
    record_number: str            # 记录编号（主键，TEXT类型，格式：YYYYMMDD+NNNN，如202606290001）
    bottle_number: str            # 试剂瓶编号（TEXT类型，关联试剂瓶表）
    user: str                     # 领用人（文本类型）
    reagent_name: Optional[str] = None    # 试剂名称（文本类型）
    cas_number: Optional[str] = None      # CAS号（文本类型）
    production_date: Optional[str] = None # 生产日期（ISO格式字符串）
    borrow_time: Optional[str] = None     # 领用时间（文本格式：YYYY/MM/DD HH:MM）
    borrow_status: Optional[str] = None    # 借出状态（待审批/已批准/已拒绝/已归还）
    borrow_qty: Optional[float] = None     # 借出数量
    approver: Optional[str] = None        # 审批人（文本类型，管控试剂必填）
    approver_id: Optional[str] = None     # 审批人 user_id
    approval_file: Optional[str] = None   # 审批记录上传（文件路径）
    approved: Optional[bool] = None       # 是否通过审批（复选框类型）
    is_controlled: Optional[int] = None    # 是否管控试剂（0=否，1=是）
    is_violation: Optional[int] = None     # 是否违规借出（0=否，1=是）
    id: Optional[int] = None       # 自增主键