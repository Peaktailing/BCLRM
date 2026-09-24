"""审计日志便捷写入工具

任何关键操作后调用 audit(...) 记录操作留痕；
写入失败不影响主业务流程（静默降级，仅记录错误日志）。
"""
from typing import Optional

from utils.error_handler import logger


def audit(
    operator: Optional[str],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    """记录一条审计日志（纯追加，失败不影响主流程）

    Args:
        operator: 操作人（用户名）
        action: 操作类型，如 领用 / 归还 / 入库 / 审批通过 / 登录 / 修改密码
        target_type: 目标类型（bottle / order / plan / user ...）
        target_id: 目标标识（瓶号 / 单号 / 用户名 ...）
        detail: 摘要说明
    """
    try:
        from services.base.operation_log_service import operation_log_service
        operation_log_service.create({
            "operator": operator or "未知",
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id) if target_id is not None else None,
            "detail": detail,
        })
    except Exception as e:
        logger.error(f"审计日志写入失败 action={action}: {e}", exception=e)
