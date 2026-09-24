"""领用记录表数据模型

对应 SQLite 表：borrow_record
"""
from pydantic import BaseModel
from typing import Optional


class BorrowRecord(BaseModel):
    """领用记录数据模型

    记录所有试剂领用操作，用于追踪试剂的使用历史和责任归属。
    """
    record_number: Optional[str] = None      # 记录编号（格式：YYYYMMDD+NNNN）
    bottle_number: Optional[str] = None      # 试剂瓶编号（关联试剂瓶表）
    user: Optional[str] = None               # 领用人
    reagent_name: Optional[str] = None       # 试剂名称
    cas_number: Optional[str] = None         # CAS号
    production_date: Optional[str] = None    # 生产日期
    borrow_time: Optional[str] = None        # 领用时间（YYYY/MM/DD HH:MM）
    borrow_quantity: Optional[float] = None  # 领用数量（用于归还超量校验）
    course_id: Optional[int] = None          # 关联实验课程ID（experiment_course.id）
    item_id: Optional[int] = None            # 关联实验项目ID（experiment_item.id）
    approver: Optional[str] = None           # 审批人（管控试剂必填）
    approval_file: Optional[str] = None      # 审批记录上传（文件路径）
    approved: Optional[bool] = None          # 是否通过审批
    is_controlled: Optional[int] = None      # 是否管控试剂（0=否，1=是）
    is_violation: Optional[int] = None       # 是否违规借出（0=否，1=是）
    id: Optional[int] = None                 # 自增主键
