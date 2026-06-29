"""人员信息表数据模型

对应 SQLite 表：person

字段映射说明：
- 用户ID -> user_id (唯一字符串标识)
- 姓名 -> name
- 密码 -> password
- 角色 -> role (super_admin/admin/teacher/student)
- 部门 -> department
- 电话 -> phone
- 学号/工号 -> student_or_work_id (用于登录)
- 显示名称 -> display_name
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class Person:
    """人员信息数据模型

    存储系统用户信息，包括领用人、审批人等。
    """
    name: Optional[str] = None                 # 姓名（文本类型）
    user_id: Optional[str] = None              # 用户ID（唯一字符串标识）
    password: Optional[str] = None             # 密码
    role: Optional[str] = None                 # 角色: super_admin/admin/teacher/student
    department: Optional[str] = None           # 部门（文本类型）
    phone: Optional[str] = None                # 电话（文本类型）
    student_or_work_id: Optional[str] = None   # 学号/工号（用于登录）
    display_name: Optional[str] = None         # 显示名称
    id: Optional[int] = None                   # 自增主键