"""存储要求表数据模型

对应 SQLite 表：storage_requirement
"""
from pydantic import BaseModel
from typing import Optional


class StorageRequirement(BaseModel):
    """存储要求数据模型

    存储试剂的存储条件要求，如：冷藏、避光、常温等。
    """
    name: Optional[str] = None
    description: Optional[str] = None
    id: Optional[int] = None