"""人员信息表数据模型

对应 SQLite 表：person
"""
from pydantic import BaseModel
from typing import Optional


class Person(BaseModel):
    """人员信息数据模型

    存储系统用户信息，包括领用人、审批人等。
    """
    name: Optional[str] = None               # 姓名
    role: Optional[str] = None               # 角色（super_admin/admin/teacher/user）
    department: Optional[str] = None         # 部门
    phone: Optional[str] = None              # 电话
    student_or_work_id: Optional[str] = None  # 学号/工号
    password_hash: Optional[str] = None      # 密码哈希（PBKDF2-HMAC-SHA256）
    id: Optional[int] = None                 # 自增主键
