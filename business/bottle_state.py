"""试剂瓶状态机（单一事实来源）。

统一管理试剂瓶的两个状态标志：
- ``borrowable_flag``（可借状态）：可借 / 已借出 / 耗尽
- ``expired_flag``（过期状态）：正常 / 即将过期 / 已过期

原先这些取值散落在 borrow / return / inventory / query 等多个服务中，
容易出现魔法字符串与规则不一致。本模块将它们收敛为枚举与纯函数，
所有赋值与判定都应经由这里，禁止在业务代码中再写死状态字符串。
"""
from __future__ import annotations

from enum import Enum


class BorrowableStatus(str, Enum):
    """可借状态：``borrowable_flag`` 的取值集合。"""

    BORROWABLE = "可借"
    BORROWED = "已借出"
    DEPLETED = "耗尽"
    EMPTY = "空瓶"          # 试剂已用完（归还时比例 0%），瓶子待报废


class ExpiryStatus(str, Enum):
    """过期状态：``expired_flag`` 的取值集合。"""

    NORMAL = "正常"
    EXPIRING = "即将过期"
    EXPIRED = "已过期"


class ScrapStatus(str, Enum):
    """报废状态：``scrap_flag`` 的取值集合。"""

    PENDING = "待报废"      # 已进入待报废清单，等待处置
    SCRAPPED = "已报废"     # 已处置完成


def borrowable_flag_on_inbound(remaining_quantity: float) -> str:
    """入库时根据剩余量确定可借状态：有量即可借，无量为耗尽。"""
    return BorrowableStatus.BORROWABLE if remaining_quantity > 0 else BorrowableStatus.DEPLETED


def borrowable_flag_on_return(remaining_quantity: float) -> str:
    """归还时根据剩余量确定可借状态：有量即可借，无量为耗尽。"""
    return BorrowableStatus.BORROWABLE if remaining_quantity > 0 else BorrowableStatus.DEPLETED


def borrowable_flag_on_borrow() -> str:
    """借出后状态固定为「已借出」。"""
    return BorrowableStatus.BORROWED


def is_borrowable(flag) -> bool:
    """判断可借状态是否为「可借」（其余状态均不可借出）。"""
    return flag == BorrowableStatus.BORROWABLE


def is_expired(flag) -> bool:
    """判断过期状态是否为「已过期」。"""
    return flag == ExpiryStatus.EXPIRED


def recompute_borrowable(bottle) -> tuple:
    """集中「量 / 过期 / 报废」三要素重算可借状态（纯函数，不写库）。

    规则：
    - scrap_flag == 待报废 → flag=「空瓶」
    - remaining_quantity <= 0（未报废）→ flag=「耗尽」
    - 其余 → flag=「可借」
    - borrowable_check：仅有量、未过期、未报废且 flag 为「可借」时为 True

    注意：本函数不改写「已借出」（是否处于借出中由调用方结合借还流程判定），
    已过期瓶的 flag 保持原判定结果、仅将 check 置 False（与 check_and_update
    的既有约定一致：过期信息由 expired_flag 表达，视图层优先展示）。

    Args:
        bottle: 具备 remaining_quantity / expired_flag / scrap_flag /
                borrowable_flag 属性的试剂瓶对象（ORM/Pydantic/轻量视图均可）

    Returns:
        tuple[str, bool]: (borrowable_flag, borrowable_check)
    """
    scrap = getattr(bottle, "scrap_flag", None) or ""
    remaining = float(getattr(bottle, "remaining_quantity", 0) or 0)
    expired = getattr(bottle, "expired_flag", None) == ExpiryStatus.EXPIRED

    if scrap == ScrapStatus.PENDING:
        flag = BorrowableStatus.EMPTY
    elif remaining <= 0:
        flag = BorrowableStatus.DEPLETED
    else:
        flag = BorrowableStatus.BORROWABLE

    check = (
        remaining > 0
        and not expired
        and not scrap
        and flag == BorrowableStatus.BORROWABLE
    )
    return flag.value, check


def is_borrowable_now(bottle) -> bool:
    """判断试剂瓶当前是否真正可借（量 / 过期 / 报废 / flag 四要素综合）。

    与 ``recompute_borrowable`` 的 check 判定一致，额外要求
    ``borrowable_flag == 可借``，用于对存量脏行（check=1 但已过期/已报废）
    做查询侧二次过滤。
    """
    flag, check = recompute_borrowable(bottle)
    return check and flag == BorrowableStatus.BORROWABLE
