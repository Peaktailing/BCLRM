"""领用记录表数据模型

对应 SQLite 表：borrow_record
"""
from pydantic import BaseModel
from typing import Optional


class BorrowRecord(BaseModel):
    """领用记录数据模型

    记录所有试剂领用操作，用于追踪试剂的使用历史和责任归属。
    """
    record_number: Optional[str] = None
    bottle_number: Optional[str] = None
    user: Optional[str] = None
    reagent_name: Optional[str] = None
    cas_number: Optional[str] = None
    production_date: Optional[str] = None
    borrow_time: Optional[str] = None
    approver: Optional[str] = None
    approval_file: Optional[str] = None
    approved: Optional[bool] = None
    is_controlled: Optional[int] = None
    is_violation: Optional[int] = None
    id: Optional[int] = None