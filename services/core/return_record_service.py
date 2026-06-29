"""归还记录服务类

对应数据表：归还记录表 (return_record)

提供归还记录的CRUD操作和查询方法。
"""
from db.base_service import BaseService
from models.core.return_record import ReturnRecord
from utils.error_handler import logger
from typing import List, Optional


class ReturnRecordService(BaseService):
    """归还记录表服务

    继承BaseService，提供归还记录数据的增删改查操作。
    """

    def __init__(self):
        super().__init__("return_record")
        logger.info("归还记录服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[ReturnRecord]:
        """通过记录ID查询归还记录

        Args:
            record_id: 记录ID

        Returns:
            ReturnRecord对象或None
        """
        record = super().get_by_id(record_id)
        if record:
            return self._parse_record(record)
        return None

    def get_by_bottle_number(self, bottle_number: str) -> List[ReturnRecord]:
        """通过试剂瓶编号查询归还记录

        Args:
            bottle_number: 试剂瓶编号（格式如：202606290001）

        Returns:
            ReturnRecord对象列表
        """
        records = super().get_all_by_field('bottle_number', bottle_number)
        return [self._parse_record(record) for record in records]

    def get_by_user(self, user: str) -> List[ReturnRecord]:
        """查询某个用户的所有归还记录

        Args:
            user: 归还人

        Returns:
            ReturnRecord对象列表
        """
        records = super().get_all_by_field('return_user', user)
        return [self._parse_record(record) for record in records]

    def get_all_parsed(self) -> List[ReturnRecord]:
        """获取所有归还记录（解析为ReturnRecord对象列表）

        Returns:
            ReturnRecord对象列表
        """
        records = self.get_all()
        return [self._parse_record(record) for record in records]

    def search_multi_condition(
        self,
        bottle_number: Optional[str] = None,
        return_user: Optional[str] = None,
        order_by: str = None
    ) -> List[ReturnRecord]:
        """多条件数据库层查询归还记录（过滤在SQL层执行）

        Args:
            bottle_number: 试剂瓶编号（精确匹配，格式如：202606290001）
            return_user: 归还人（精确匹配）
            order_by: 排序字段

        Returns:
            ReturnRecord对象列表
        """
        conditions = []

        if bottle_number is not None:
            conditions.append({
                "field": "bottle_number",
                "value": bottle_number,
                "match_type": "exact"
            })

        if return_user:
            conditions.append({
                "field": "return_user",
                "value": return_user,
                "match_type": "exact"
            })

        records = super().search_multi_condition(conditions, order_by=order_by)
        return [self._parse_record(record) for record in records]

    def _parse_record(self, record: dict) -> ReturnRecord:
        """将数据库记录解析为ReturnRecord对象

        Args:
            record: 数据库记录字典

        Returns:
            ReturnRecord对象
        """
        return ReturnRecord(
            id=record.get('id'),
            return_number=record.get('return_number', ''),
            bottle_number=record.get('bottle_number', ''),
            return_user=record.get('return_user', ""),
            return_time=record.get('return_time'),
            remaining_quantity=record.get('remaining_quantity', 0.0),
            last_update_time=record.get('last_update_time'),
            modifier=record.get('modifier')
        )

# 全局实例
return_record_service = ReturnRecordService()