"""实验课程表数据模型

对应 SQLite 表：experiment_course

来源于学院实验分组表，用于：
- 领用记录关联实验课程
- 按课程统计试剂用量与人均用量（人均 = 课程用量 ÷ 班级人数）
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExperimentCourse:
    """实验课程数据模型"""
    id: Optional[int] = None
    semester: Optional[str] = None        # 学年，如 2026-2027
    term: Optional[str] = None            # 学期，如 1
    course_name: Optional[str] = None     # 课程名称
    class_name: Optional[str] = None      # 开课班级
    major: Optional[str] = None           # 开课专业
    teacher: Optional[str] = None         # 任课教师（多位用「、」连接）
    student_count: Optional[int] = None   # 班级人数（人均用量的分母）
    location: Optional[str] = None        # 上课地点
    college: Optional[str] = None         # 开课学院

    @property
    def display_name(self) -> str:
        """下拉展示名：课程名称（班级）"""
        if self.class_name:
            return f"{self.course_name}（{self.class_name}）"
        return self.course_name or ""
