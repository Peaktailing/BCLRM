"""存储要求表数据模型

对应Teable表：存储要求表

字段映射说明：
- 名称 -> name
- 描述 -> description
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class StorageRequirement:
    """存储要求数据模型
    
    存储试剂的存储条件要求，如：冷藏、避光、常温等。
    """
    name: Optional[str] = None        # 存储要求名称（文本类型）
    description: Optional[str] = None # 描述（文本类型）
    id: Optional[str] = None       # Teable内部记录ID（系统自动生成）