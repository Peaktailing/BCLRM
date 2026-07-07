"""存储位置表数据模型

对应 SQLite 表：storage_location
"""
from pydantic import BaseModel
from typing import Optional


class StorageLocation(BaseModel):
    """存储位置数据模型

    存储试剂存放位置信息，如：A栋301室1号柜、危化品存储柜1等。
    """
    name: Optional[str] = None
    description: Optional[str] = None
    id: Optional[int] = None