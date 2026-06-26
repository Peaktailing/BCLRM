"""存储位置表数据模型

对应Teable表：存储位置表

字段映射说明：
- 名称 -> name
- 描述 -> description
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class StorageLocation:
    """存储位置数据模型
    
    存储试剂存放位置信息，如：A栋301室1号柜、危化品存储柜1等。
    """
    name: Optional[str] = None        # 存储位置名称（文本类型）
    description: Optional[str] = None # 描述（文本类型）
    id: Optional[str] = None       # Teable内部记录ID（系统自动生成）