"""生产商表数据模型

对应 SQLite 表：manufacturer
"""
from pydantic import BaseModel
from typing import Optional


class Manufacturer(BaseModel):
    """生产商数据模型

    存储试剂生产商信息，用于溯源和质量控制。
    """
    full_name: Optional[str] = None
    brand_name: Optional[str] = None
    website: Optional[str] = None
    attachment: Optional[str] = None
    id: Optional[int] = None