"""化学品信息表数据模型

对应 SQLite 表：chemical_info
"""
from pydantic import BaseModel
from typing import Optional


class ChemicalInfo(BaseModel):
    """化学品信息数据模型

    存储化学品的通用属性信息，用于统一管理化学品基础数据。
    """
    name: Optional[str] = None
    display_name: Optional[str] = None
    formula: Optional[str] = None
    cas_number: Optional[str] = None
    msds: Optional[str] = None
    reagent_type: Optional[str] = None
    storage_requirement: Optional[str] = None
    controlled_type: Optional[str] = None
    unsealed_shelf_life: Optional[int] = None
    sealed_shelf_life: Optional[int] = None
    id: Optional[int] = None