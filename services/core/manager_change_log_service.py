"""管理人变更记录数据服务类

对应数据表：manager_change_log
"""
from typing import List, Optional

from db.base_service import BaseService
from models.core.manager_change_log import ManagerChangeLog
from utils.error_handler import logger


class ManagerChangeLogService(BaseService):
    """管理人变更记录服务"""

    def __init__(self):
        super().__init__("manager_change_log")
        logger.info("管理人变更记录服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ManagerChangeLog]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[ManagerChangeLog]:
        """全部变更记录（最新在前）"""
        return [self._parse_record(record) for record in self.get_all(order_by="id DESC")]

    def get_by_bottle(self, bottle_number: str) -> List[ManagerChangeLog]:
        """按试剂瓶编号查询变更历史（最新在前）"""
        records = self.db.execute_query(
            "SELECT * FROM manager_change_log WHERE bottle_number = ? ORDER BY id DESC",
            (bottle_number,)
        )
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> ManagerChangeLog:
        return ManagerChangeLog(
            id=record.get('id'),
            bottle_number=record.get('bottle_number'),
            reagent_name=record.get('reagent_name'),
            old_manager=record.get('old_manager'),
            new_manager=record.get('new_manager'),
            reason=record.get('reason'),
            ref_type=record.get('ref_type'),
            ref_id=record.get('ref_id'),
            remark=record.get('remark'),
            operator=record.get('operator'),
            changed_at=record.get('changed_at'),
        )


# 全局实例
manager_change_log_service = ManagerChangeLogService()
