"""试剂类型表数据模型

对应 SQLite 表：reagent_type
"""
from pydantic import BaseModel
from typing import Optional


class ReagentType(BaseModel):
    """试剂类型数据模型

    存储试剂类型信息，如：分析纯、化学纯、优级纯等。
    """
    name: Optional[str] = None
    description: Optional[str] = None
    default_unsealed_shelf_life: Optional[int] = None
    default_sealed_shelf_life: Optional[int] = None
    id: Optional[int] = None