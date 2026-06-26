"""领用记录服务类

对应数据表：领用记录表 (borrow_record)

提供领用记录的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.core.borrow_record import BorrowRecord
from utils.error_handler import logger
from typing import List, Optional


class BorrowRecordService(BaseService):
    """领用记录表服务

    继承BaseService，提供领用记录数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("borrow_record")
        logger.info("领用记录服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[BorrowRecord]:
        """通过记录ID查询领用记录

        Args:
            record_id: 记录ID

        Returns:
            BorrowRecord对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_bottle_number(self, bottle_number: int) -> List[BorrowRecord]:
        """查询某个试剂瓶的所有领用记录

        Args:
            bottle_number: 试剂瓶编号

        Returns:
            BorrowRecord对象列表
        """
        records = super().get_all_by_field('bottle_number', bottle_number)
        return [self._parse_record(record) for record in records]

    def get_by_user(self, user: str) -> List[BorrowRecord]:
        """查询某个用户的所有领用记录

        Args:
            user: 领用人

        Returns:
            BorrowRecord对象列表
        """
        records = super().get_all_by_field('user', user)
        return [self._parse_record(record) for record in records]

    def get_pending_approvals(self) -> List[BorrowRecord]:
        """获取所有待审批的领用记录

        Returns:
            BorrowRecord对象列表
        """
        # SQLite中 NULL 检查需要用 IS NULL
        query = "SELECT * FROM borrow_record WHERE approved IS NULL"
        try:
            records = self.db.execute_query(query)
            return [self._parse_record(record) for record in records]
        except Exception as e:
            logger.error(f"获取待审批记录失败: {str(e)}", exception=e)
            return []

    def get_all_parsed(self) -> List[BorrowRecord]:
        """获取所有领用记录（解析为BorrowRecord对象列表）

        Returns:
            BorrowRecord对象列表
        """
        records = self.get_all()
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> BorrowRecord:
        """将数据库记录解析为BorrowRecord对象

        Args:
            record: 数据库记录字典

        Returns:
            BorrowRecord对象
        """
        return BorrowRecord(
            id=record.get('id'),
            record_number=record.get('record_number', ""),
            bottle_number=record.get('bottle_number', 0),
            reagent_name=record.get('reagent_name'),
            user=record.get('user', ""),
            cas_number=record.get('cas_number'),
            production_date=record.get('production_date'),
            borrow_time=record.get('borrow_time'),
            approver=record.get('approver'),
            approval_file=record.get('approval_file'),
            approved=record.get('approved')
        )

# 全局实例
borrow_record_service = BorrowRecordService()