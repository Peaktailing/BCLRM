"""实验项目与用量台账数据模型

- experiment_project          实验项目（科研/毕设等非课程类实验）
- experiment_reagent_usage    实验试剂用量台账（归还时落账，供统计与留痕）
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExperimentProject:
    """实验项目"""
    id: Optional[int] = None
    project_name: Optional[str] = None   # 项目名称
    semester: Optional[str] = None       # 所属学年（如 2026-2027）
    teacher: Optional[str] = None        # 负责教师
    description: Optional[str] = None    # 项目描述


@dataclass
class ExperimentReagentUsage:
    """实验试剂用量台账"""
    id: Optional[int] = None
    project_id: Optional[int] = None             # 关联实验项目（非课程类）
    reagent_name: Optional[str] = None
    cas_number: Optional[str] = None
    usage_quantity: Optional[float] = None       # 本次用量（= 领用量 - 还入量）
    usage_date: Optional[str] = None             # 归还时间
    course_name: Optional[str] = None            # 关联课程（课程领用时填写）
    item_name: Optional[str] = None              # 关联实验
    semester: Optional[str] = None               # 归属学年
