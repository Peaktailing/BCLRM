"""实验方案 / 默认用量 / 实验进度状态 服务类

对应数据表：
- experiment_plan           实验方案（方案文本，按「课程名 + 实验名」跨学年复用）
- experiment_default_usage  实验默认用量（人均用量）
- experiment_item_status    实验进度状态（按学年）
"""
from typing import List, Optional

from db.base_service import BaseService
from models.base.experiment_plan import (
    ExperimentDefaultUsage,
    ExperimentItemStatus,
    ExperimentPlan,
    STATUS_NOT_BORROWED,
)
from utils.error_handler import logger


class ExperimentPlanService(BaseService):
    """实验方案表服务"""

    def __init__(self):
        super().__init__("experiment_plan")
        logger.info("实验方案服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ExperimentPlan]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_by_item(self, course_name: str, item_name: str) -> Optional[ExperimentPlan]:
        """按（课程名 + 实验名）取方案（跨学年复用同一份）"""
        for record in super().get_all_by_field("course_name", course_name):
            if record.get("item_name") == item_name:
                return self._parse_record(record)
        return None

    def upsert(self, course_name: str, item_name: str, plan_text: Optional[str]) -> Optional[int]:
        """新增或更新方案，返回记录 id（失败返回 None）"""
        existing = self.get_by_item(course_name, item_name)
        if existing:
            ok = self.update(existing.id, {"plan_text": plan_text})
            return existing.id if ok else None
        record_id = self.create({
            "course_name": course_name,
            "item_name": item_name,
            "plan_text": plan_text,
        })
        return record_id or None

    def _parse_record(self, record: dict) -> ExperimentPlan:
        return ExperimentPlan(
            id=record.get("id"),
            course_name=record.get("course_name"),
            item_name=record.get("item_name"),
            plan_text=record.get("plan_text"),
        )


class ExperimentDefaultUsageService(BaseService):
    """实验默认用量表服务"""

    def __init__(self):
        super().__init__("experiment_default_usage")
        logger.info("实验默认用量服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ExperimentDefaultUsage]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_by_item(self, course_name: str, item_name: str) -> List[ExperimentDefaultUsage]:
        """按（课程名 + 实验名）取默认用量列表"""
        return [
            self._parse_record(record)
            for record in super().get_all_by_field("course_name", course_name)
            if record.get("item_name") == item_name
        ]

    def upsert(self, payload: dict) -> bool:
        """按（课程名 + 实验名 + 试剂名）新增或更新"""
        course_name = payload.get("course_name")
        item_name = payload.get("item_name")
        reagent_name = payload.get("reagent_name")
        existing = next(
            (
                usage for usage in self.get_by_item(course_name, item_name)
                if usage.reagent_name == reagent_name
            ),
            None,
        )
        if existing:
            fields = {
                key: value for key, value in payload.items()
                if key not in ("course_name", "item_name", "reagent_name")
            }
            return bool(self.update(existing.id, fields))
        return bool(self.create(payload))

    def delete_by_item(self, course_name: str, item_name: str) -> bool:
        """删除某实验的全部默认用量（用于整体覆盖保存）"""
        ok = True
        for usage in self.get_by_item(course_name, item_name):
            ok = bool(self.delete(usage.id)) and ok
        return ok

    def _parse_record(self, record: dict) -> ExperimentDefaultUsage:
        return ExperimentDefaultUsage(
            id=record.get("id"),
            course_name=record.get("course_name"),
            item_name=record.get("item_name"),
            reagent_name=record.get("reagent_name"),
            qty_per_person=record.get("qty_per_person"),
            unit=record.get("unit"),
            base_qty=record.get("base_qty"),
            base_student_count=record.get("base_student_count"),
            source=record.get("source"),
        )


class ExperimentItemStatusService(BaseService):
    """实验进度状态表服务"""

    def __init__(self):
        super().__init__("experiment_item_status")
        logger.info("实验进度状态服务初始化完成")

    def get_status(
        self,
        semester: Optional[str],
        course_name: str,
        item_name: str
    ) -> str:
        """取某实验的进度状态（无记录时视为「未领用」）"""
        for record in super().get_all_by_field("course_name", course_name):
            if (
                record.get("item_name") == item_name
                and (record.get("semester") or None) == (semester or None)
            ):
                return record.get("status") or STATUS_NOT_BORROWED
        return STATUS_NOT_BORROWED

    def get_by_semester(self, semester: Optional[str]) -> List[ExperimentItemStatus]:
        """按学年取全部实验状态"""
        if semester:
            records = super().get_all_by_field("semester", semester)
        else:
            records = self.get_all()
        return [self._parse_record(record) for record in records]

    def set_status(
        self,
        semester: Optional[str],
        course_name: str,
        item_name: str,
        status: str,
        borrow_time: Optional[str] = None,
        return_time: Optional[str] = None
    ) -> bool:
        """写入/更新实验进度状态"""
        if not course_name or not item_name:
            return False

        payload = {
            "semester": semester,
            "course_name": course_name,
            "item_name": item_name,
            "status": status,
        }
        if borrow_time is not None:
            payload["last_borrow_time"] = borrow_time
        if return_time is not None:
            payload["last_return_time"] = return_time

        existing = None
        for record in super().get_all_by_field("course_name", course_name):
            if (
                record.get("item_name") == item_name
                and (record.get("semester") or None) == (semester or None)
            ):
                existing = record
                break

        if existing:
            return bool(self.update(existing.get("id"), payload))
        return bool(self.create(payload))

    def _parse_record(self, record: dict) -> ExperimentItemStatus:
        return ExperimentItemStatus(
            id=record.get("id"),
            semester=record.get("semester"),
            course_name=record.get("course_name"),
            item_name=record.get("item_name"),
            status=record.get("status"),
            last_borrow_time=record.get("last_borrow_time"),
            last_return_time=record.get("last_return_time"),
        )


# 全局实例
experiment_plan_service = ExperimentPlanService()
experiment_default_usage_service = ExperimentDefaultUsageService()
experiment_item_status_service = ExperimentItemStatusService()
