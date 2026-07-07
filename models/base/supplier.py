"""供应商表数据模型

对应 SQLite 表：supplier
"""
from pydantic import BaseModel
from typing import Optional


class Supplier(BaseModel):
    """供应商数据模型

    存储试剂供应商信息，用于入库时选择供应商。
    """
    name: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    id: Optional[int] = None