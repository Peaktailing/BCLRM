"""人员信息表数据模型

对应 SQLite 表：person
"""
from pydantic import BaseModel, Field
from typing import Optional


class Person(BaseModel):
    """人员信息数据模型

    存储系统用户信息，包括领用人、审批人等。
    """
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    student_or_work_id: Optional[str] = None
    password_hash: Optional[str] = None
    id: Optional[int] = None