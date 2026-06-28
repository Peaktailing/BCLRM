"""供应商表数据模型

对应 SQLite 表：supplier

字段映射说明：
- 名称 -> name
- 联系人 -> contact
- 电话 -> phone
- 地址 -> address
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class Supplier:
    """供应商数据模型
    
    存储试剂供应商信息，用于入库时选择供应商。
    """
    name: str                     # 供应商名称（文本类型，主键）
    contact: Optional[str] = None # 联系人（文本类型）
    phone: Optional[str] = None   # 电话（文本类型）
    address: Optional[str] = None # 地址（文本类型）
    id: Optional[int] = None       # 自增主键