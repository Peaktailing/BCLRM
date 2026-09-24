"""试剂瓶显示状态派生工具

放在 utils 层，供 service / business 各层共用，避免 services 反向依赖 business。

状态口径（与 business/bottle_state 一致）：
- 已过期（优先级最高）
- 空瓶（试剂用完、待报废）
- 耗尽
- 已借出
- 可借
"""
from typing import Any


def derive_bottle_status(bottle: Any) -> str:
    """根据 borrowable_flag / expired_flag 等字段派生显示状态

    Args:
        bottle: 试剂瓶对象（ReagentBottle 或含同名属性的对象）

    Returns:
        显示状态字符串：已过期 / 空瓶 / 耗尽 / 已借出 / 可借
    """
    if getattr(bottle, "expired_flag", None) == "已过期":
        return "已过期"

    flag = getattr(bottle, "borrowable_flag", None)
    if flag in ("可借", "已借出", "耗尽", "空瓶"):
        return flag

    # 兜底：按可借布尔标记与剩余量派生（兼容旧数据）
    if getattr(bottle, "borrowable_check", None) is False:
        return "已借出"
    if not getattr(bottle, "remaining_quantity", None):
        return "耗尽"
    return "可借"
