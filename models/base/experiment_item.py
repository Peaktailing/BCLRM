"""实验项目（课程下的实验）数据模型

对应 SQLite 表：experiment_item
来源于学院实验分组表的「实验项目」列，如「实验一 仪器认领、洗涤和使用方法」。
按 (学年, 课程名, 实验名) 唯一，同一课程的不同班级共享同一份实验列表。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExperimentItem:
    id: Optional[int] = None
    semester: Optional[str] = None       # 学年，如 2026-2027
    course_name: Optional[str] = None    # 所属课程名
    seq: Optional[int] = None            # 实验序号（从 1 开始）
    item_name: Optional[str] = None      # 实验名称
