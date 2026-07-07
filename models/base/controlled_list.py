"""管控化学品名录表数据模型

对应 SQLite 表：controlled_list
"""
from pydantic import BaseModel
from typing import Optional


class ControlledList(BaseModel):
    """管控化学品名录数据模型

    存储需要特殊管控的化学品列表，用于在领用时自动判断是否需要审批。
    """
    chemical_name: Optional[str] = None
    alias: Optional[str] = None
    cas_number: Optional[str] = None
    dangerous_type: Optional[str] = None
    id: Optional[int] = None