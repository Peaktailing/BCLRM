"""人员信息表数据模型

对应 SQLite 表：person

字段映射说明：
- 姓名 -> name
- 角色 -> role
- 部门 -> department
- 电话 -> phone
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class Person:
    """人员信息数据模型
    
    存储系统用户信息，包括领用人、审批人等。
    """
    name: Optional[str] = None        # 姓名（文本类型）
    role: Optional[str] = None        # 角色（文本类型，如：admin、user）
    department: Optional[str] = None  # 部门（文本类型）
    phone: Optional[str] = None       # 电话（文本类型）
    id: Optional[str] = None       # Teable内部记录ID（系统自动生成）