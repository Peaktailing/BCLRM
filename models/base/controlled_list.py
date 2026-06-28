"""管控化学品名录表数据模型

对应 SQLite 表：controlled_list

字段映射说明：
- 化学品名称 -> chemical_name
- 化学品别名 -> alias
- CAS号 -> cas_number
- 危化品类型 -> dangerous_type
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class ControlledList:
    """管控化学品名录数据模型
    
    存储需要特殊管控的化学品列表，用于在领用时自动判断是否需要审批。
    """
    chemical_name: Optional[str] = None # 化学品名称（文本类型，主键）
    alias: Optional[str] = None         # 化学品别名（文本类型）
    cas_number: Optional[str] = None     # CAS编号（文本类型）
    dangerous_type: Optional[str] = None # 危化品类型（文本类型，如：剧毒、易制爆、易制毒）
    id: Optional[int] = None       # 自增主键