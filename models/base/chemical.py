"""化学品信息表数据模型

对应 SQLite 表：chemical_info

字段映射说明：
- 化学品名称 -> name
- 通用显示名称 -> display_name
- 化学式 -> formula（纯文本）
- CAS号 -> cas_number（纯文本，避免被误认为日期）
- MSDS -> msds（附件）
- 试剂类型 -> reagent_type
- 存储要求 -> storage_requirement
- 管控试剂类型 -> controlled_type（匹配项）
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class ChemicalInfo:
    """化学品信息数据模型
    
    存储化学品的通用属性信息，用于统一管理化学品基础数据。
    """
    name: Optional[str] = None           # 化学品名称（文本类型）
    display_name: Optional[str] = None   # 通用显示名称（文本类型）
    formula: Optional[str] = None        # 化学式（纯文本）
    cas_number: Optional[str] = None     # CAS号（纯文本，避免被误认为日期）
    msds: Optional[str] = None           # MSDS附件（附件类型）
    reagent_type: Optional[str] = None  # 试剂类型（逗号分隔多个类型，无外键约束）
    storage_requirement: Optional[str] = None  # 存储要求（文本类型，关联存储要求表）
    controlled_type: Optional[str] = None      # 管控试剂类型（文本类型，匹配管控名录）
    unsealed_shelf_life: Optional[int] = None  # 未启封有效时长（天）
    sealed_shelf_life: Optional[int] = None    # 启封有效时长（天）
    id: Optional[int] = None            # 自增主键