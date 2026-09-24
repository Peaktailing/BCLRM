"""归还记录表数据模型

对应 SQLite 表：return_record
"""
from pydantic import BaseModel
from typing import Optional


class ReturnRecord(BaseModel):
    """归还记录数据模型

    记录所有试剂归还操作，更新试剂瓶的剩余量状态。
    """
    return_number: Optional[str] = None      # 归还记录编号（YYYYMMDD+NNNN）
    bottle_number: Optional[str] = None      # 试剂瓶编号（关联试剂瓶表）
    return_user: Optional[str] = None        # 归还人
    return_time: Optional[str] = None        # 归还时间（YYYY/MM/DD HH:MM）
    remaining_quantity: Optional[float] = None  # 归还时余量
    usage_quantity: Optional[float] = None      # 本次实际用量（= 领用量 - 还入量）
    linked_borrow_record_number: Optional[str] = None  # 关联领用记录号
    last_update_time: Optional[str] = None   # 最后更新时间
    modifier: Optional[str] = None           # 修改人
    id: Optional[int] = None                 # 自增主键
