"""归还记录表数据模型

对应Teable表：归还记录表
表ID: tblJhsv7PMN64TDrI1P

字段映射说明：
- 归还记录 编号 -> return_number
- 试剂瓶编号 -> bottle_number
- 归还人 -> return_user
- 归还时间 -> return_time
- 归还时余量 -> remaining_quantity
- 最后更新时间 -> last_update_time
- 修改人 -> modifier
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class ReturnRecord:
    """归还记录数据模型
    
    记录所有试剂归还操作，更新试剂瓶的剩余量状态。
    """
    return_number: Optional[int] = None   # 归还记录编号（数字类型，格式：时间戳）
    bottle_number: Optional[int] = None   # 试剂瓶编号（数字类型，关联试剂瓶表）
    return_user: Optional[str] = None     # 归还人（文本类型）
    return_time: Optional[str] = None     # 归还时间（文本格式：YYYY/MM/DD HH:MM）
    remaining_quantity: Optional[float] = None # 归还时余量（数字类型）
    last_update_time: Optional[str] = None    # 最后更新时间（文本格式）
    modifier: Optional[str] = None        # 修改人（文本类型）
    id: Optional[str] = None       # Teable内部记录ID（系统自动生成）