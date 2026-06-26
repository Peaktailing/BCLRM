"""试剂类型表数据模型

对应 SQLite 表：reagent_type

字段映射说明：
- 名称 -> name
- 描述 -> description
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class ReagentType:
    """试剂类型数据模型
    
    存储试剂类型信息，如：分析纯、化学纯、优级纯等。
    """
    name: Optional[str] = None        # 试剂类型名称（文本类型）
    description: Optional[str] = None # 描述（文本类型）
    id: Optional[str] = None       # Teable内部记录ID（系统自动生成）