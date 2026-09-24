"""实验方案 / 默认用量 / 实验进度状态 数据模型

- experiment_plan           实验方案（方案文本，按「课程名 + 实验名」跨学年复用）
- experiment_default_usage  实验默认用量（人均用量，领用时按班级人数折算）
- experiment_item_status    实验进度状态（按学年记录：未领用 / 已借出试剂 / 已还入试剂）
"""
from dataclasses import dataclass
from typing import Optional

# 实验进度状态
STATUS_NOT_BORROWED = "未领用"
STATUS_BORROWED = "已借出试剂"
STATUS_RETURNED = "已还入试剂"

# 默认用量来源
SOURCE_MANUAL = "手动"
SOURCE_HISTORY = "历史工单"


@dataclass
class ExperimentPlan:
    """实验方案（默认方案文本）"""
    id: Optional[int] = None
    course_name: Optional[str] = None
    item_name: Optional[str] = None
    plan_text: Optional[str] = None


@dataclass
class ExperimentDefaultUsage:
    """实验默认用量（人均用量）"""
    id: Optional[int] = None
    course_name: Optional[str] = None
    item_name: Optional[str] = None
    reagent_name: Optional[str] = None
    qty_per_person: Optional[float] = None      # 人均用量
    unit: Optional[str] = None                  # 单位（如 g / mL）
    base_qty: Optional[float] = None            # 来源：整班原始量（历史工单）
    base_student_count: Optional[int] = None    # 来源：导入时的人数
    source: Optional[str] = None                # 手动 / 历史工单


@dataclass
class ExperimentItemStatus:
    """实验进度状态（按学年）"""
    id: Optional[int] = None
    semester: Optional[str] = None
    course_name: Optional[str] = None
    item_name: Optional[str] = None
    status: Optional[str] = None                # 未领用 / 已借出试剂 / 已还入试剂
    last_borrow_time: Optional[str] = None
    last_return_time: Optional[str] = None
