"""审计日志服务类

对应数据表：operation_log（纯追加写入，不提供修改/删除）
"""
from typing import List, Optional

from db.base_service import BaseService
from utils.error_handler import logger


class OperationLogService(BaseService):
    """审计日志表服务"""

    def __init__(self):
        super().__init__("operation_log")
        logger.info("审计日志服务初始化完成")

    def list_logs(
        self,
        action: Optional[str] = None,
        operator: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        """按条件查询审计日志（时间倒序）

        Args:
            action: 操作类型过滤（如 领用 / 归还 / 审批通过）
            operator: 操作人过滤
            limit: 返回条数上限
        """
        sql = "SELECT * FROM operation_log WHERE 1=1"
        params: List = []
        if action:
            sql += " AND action = ?"
            params.append(action)
        if operator:
            sql += " AND operator = ?"
            params.append(operator)
        sql += f" ORDER BY id DESC LIMIT {int(limit)}"
        return self.db.execute_query(sql, tuple(params)) or []


# 全局实例
operation_log_service = OperationLogService()
