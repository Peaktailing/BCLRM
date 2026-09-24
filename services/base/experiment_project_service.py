"""实验项目与用量台账服务类

对应数据表：
- experiment_project          实验项目
- experiment_reagent_usage    实验试剂用量台账
"""
from typing import List, Optional

from db.base_service import BaseService
from models.base.experiment_project import ExperimentProject, ExperimentReagentUsage
from utils.error_handler import logger


class ExperimentProjectService(BaseService):
    """实验项目服务"""

    def __init__(self):
        super().__init__("experiment_project")
        logger.info("实验项目服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ExperimentProject]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[ExperimentProject]:
        return [self._parse_record(r) for r in self.get_all(order_by="id DESC")]

    def get_by_semester(self, semester: Optional[str] = None) -> List[ExperimentProject]:
        records = (
            super().get_all_by_field("semester", semester)
            if semester else self.get_all()
        )
        return [self._parse_record(r) for r in records]

    def _parse_record(self, record: dict) -> ExperimentProject:
        return ExperimentProject(
            id=record.get("id"),
            project_name=record.get("project_name"),
            semester=record.get("semester"),
            teacher=record.get("teacher"),
            description=record.get("description"),
        )


class ExperimentReagentUsageService(BaseService):
    """实验试剂用量台账服务（纯追加）"""

    def __init__(self):
        super().__init__("experiment_reagent_usage")
        logger.info("用量台账服务初始化完成")

    def add_usage(self, payload: dict) -> bool:
        """落账一条用量记录"""
        return bool(self.create(payload))

    def list_by_semester(
        self, semester: Optional[str] = None, limit: int = 500
    ) -> List[ExperimentReagentUsage]:
        """按学年查询台账（时间倒序）"""
        if semester:
            records = self.db.execute_query(
                "SELECT * FROM experiment_reagent_usage WHERE semester = ? "
                "ORDER BY id DESC LIMIT ?",
                (semester, int(limit)),
            )
        else:
            records = self.get_all(order_by="id DESC")
        return [self._parse_record(r) for r in (records or [])]

    def _parse_record(self, record: dict) -> ExperimentReagentUsage:
        return ExperimentReagentUsage(
            id=record.get("id"),
            project_id=record.get("project_id"),
            reagent_name=record.get("reagent_name"),
            cas_number=record.get("cas_number"),
            usage_quantity=record.get("usage_quantity"),
            usage_date=record.get("usage_date"),
            course_name=record.get("course_name"),
            item_name=record.get("item_name"),
            semester=record.get("semester"),
        )


# 全局实例
experiment_project_service = ExperimentProjectService()
experiment_reagent_usage_service = ExperimentReagentUsageService()
