"""归还记录表数据模型

对应 SQLite 表：return_record
"""
from pydantic import BaseModel
from typing import Optional


class ReturnRecord(BaseModel):
    """归还记录数据模型

    记录所有试剂归还操作，更新试剂瓶的剩余量状态。
    """
    return_number: Optional[str] = None
    bottle_number: Optional[str] = None
    return_user: Optional[str] = None
    return_time: Optional[str] = None
    remaining_quantity: Optional[float] = None
    last_update_time: Optional[str] = None
    modifier: Optional[str] = None
    id: Optional[int] = None