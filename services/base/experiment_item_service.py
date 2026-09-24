"""实验项目服务类

对应数据表：实验项目表 (experiment_item)
"""
from typing import List, Optional

from db.base_service import BaseService
from models.base.experiment_item import ExperimentItem
from utils.error_handler import logger


class ExperimentItemService(BaseService):
    """实验项目表服务"""

    def __init__(self):
        super().__init__("experiment_item")
        logger.info("实验项目服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ExperimentItem]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[ExperimentItem]:
        """全部实验项目"""
        return [self._parse_record(record) for record in self.get_all()]

    def get_by_course(self, course_name: str, semester: Optional[str] = None) -> List[ExperimentItem]:
        """查询某课程（可按学年限定）的实验项目，按序号排序

        同一「实验名」只保留一条（跨学年去重），避免往年导入留下的同名记录重复展示。
        """
        records = super().get_all_by_field('course_name', course_name)
        items = [self._parse_record(record) for record in records]
        if semester:
            items = [item for item in items if item.semester == semester]

        deduped: List[ExperimentItem] = []
        seen = set()
        for item in sorted(items, key=lambda x: (x.seq is None, x.seq or 0)):
            if item.item_name in seen:
                continue
            seen.add(item.item_name)
            deduped.append(item)
        return deduped

    def get_by_semester(self, semester: Optional[str] = None) -> List[ExperimentItem]:
        """按学年查询实验项目；不传则返回全部"""
        if semester:
            records = super().get_all_by_field('semester', semester)
        else:
            records = self.get_all()
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> ExperimentItem:
        return ExperimentItem(
            id=record.get('id'),
            semester=record.get('semester'),
            course_name=record.get('course_name'),
            seq=record.get('seq'),
            item_name=record.get('item_name'),
        )


# 全局实例
experiment_item_service = ExperimentItemService()
