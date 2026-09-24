"""实验课程服务类

对应数据表：实验课程表 (experiment_course)
"""
from typing import List, Optional

from db.base_service import BaseService
from models.base.experiment_course import ExperimentCourse
from utils.error_handler import logger


class ExperimentCourseService(BaseService):
    """实验课程表服务"""

    def __init__(self):
        super().__init__("experiment_course")
        logger.info("实验课程服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ExperimentCourse]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[ExperimentCourse]:
        """获取全部课程（解析为对象）"""
        return [self._parse_record(record) for record in self.get_all()]

    def get_by_semester(self, semester: Optional[str] = None) -> List[ExperimentCourse]:
        """按学年查询课程；不传则返回全部"""
        if semester:
            records = super().get_all_by_field('semester', semester)
        else:
            records = self.get_all()
        return [self._parse_record(record) for record in records]

    def list_semesters(self) -> List[str]:
        """列出已有的学年（倒序）"""
        values = super().get_distinct_values('semester')
        return sorted([v for v in values if v], reverse=True)

    def _parse_record(self, record: dict) -> ExperimentCourse:
        return ExperimentCourse(
            id=record.get('id'),
            semester=record.get('semester'),
            term=record.get('term'),
            course_name=record.get('course_name'),
            class_name=record.get('class_name'),
            major=record.get('major'),
            teacher=record.get('teacher'),
            student_count=record.get('student_count'),
            location=record.get('location'),
            college=record.get('college'),
        )


# 全局实例
experiment_course_service = ExperimentCourseService()
