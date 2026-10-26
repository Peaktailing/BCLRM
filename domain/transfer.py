"""调拨的状态常量与判定规则（纯逻辑，不认识 SQL 与 Streamlit）。

状态机放在**领域层**而不是 models，是因为它是判定的一部分：谁能点头、
勾哪几行、整单定成什么状态，三件事共用同一套状态常量。分层规则里
``domain`` 只允许依赖自己，所以这里不 import ``models``——反过来由
``models/core/transfer_order.py`` 只用 dataclass 描述字段形状。

```
待发送 ──送──> 待点头 ──逐行勾选──> 已同意（已生效，保管权已流转）
                 │
                 ├── 全部不同意 ──> 已拒绝
                 └── 发起人撤回 ──> 已撤回
```

两条判定容易写错、且写错了没人报错，所以单独放在这里：

1. **谁能点头。** 调的是保管权，只有 ``from_manager`` 本人能答应。这一条
   **与组池逻辑故意不一致**（§14.6.1）：组池判「这张单该谁办」，同组管理员
   可以代办；保管权判「这批货归谁」，代办等于替他认下一批货。
2. **点头之后哪几行生效。** 允许部分同意——3 瓶给 2 瓶是常态，整单只能全给
   或全不给的话，现实里的折中没法表达，最后都变成「先拒了再说」。
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

# ---------------------------------------------------------------- 单状态
TRANSFER_DRAFT = "待发送"        # 建议算出来了，还没送到对方手上
TRANSFER_REQUESTED = "待点头"    # 已送到出料人，等他自己确认
TRANSFER_ACCEPTED = "已同意"     # 点头即生效，保管权已流转（不设「待执行」）
TRANSFER_REJECTED = "已拒绝"     # 一行都没同意，必附理由
TRANSFER_CANCELLED = "已撤回"    # 发起人自己收回

#: 还在办的状态。列表与计数都按这个口径，别在各处手写元组。
TRANSFER_OPEN_STATUSES = (TRANSFER_DRAFT, TRANSFER_REQUESTED)

TRANSFER_STATUSES = (
    TRANSFER_DRAFT,
    TRANSFER_REQUESTED,
    TRANSFER_ACCEPTED,
    TRANSFER_REJECTED,
    TRANSFER_CANCELLED,
)

# ---------------------------------------------------------------- 明细状态
ITEM_PENDING = "待点头"
ITEM_ACCEPTED = "已同意"
ITEM_DECLINED = "已拒绝"
ITEM_FAILED = "执行失败"   # 点了头但瓶已被借走 / 不存在，这一瓶没转成

# ---------------------------------------------------------------- 业务取值
# 变更原因（写进 manager_change_log）
REASON_SHORTFALL = "缺口调配"
REASON_MANUAL = "手工借调"
REASON_FORCED = "超管强平"

# 单据来源类型
ORIGIN_SHEET = "requirement_sheet"
ORIGIN_ORDER = "work_order"
ORIGIN_MANUAL = "manual"

# ---------------------------------------------------------------- 原因码
ANSWER_NOT_REQUESTED = "TRANSFER_NOT_REQUESTED"    # 单不在「待点头」
ANSWER_NOT_SUPPLIER = "NOT_THE_SUPPLIER"           # 不是出料人本人
ANSWER_SELF = "SAME_MANAGER"                       # 自己转给自己
ANSWER_EMPTY = "NO_PARTY"                          # 出料人或受益人为空
ANSWER_REMARK_REQUIRED = "REJECT_REMARK_REQUIRED"  # 拒绝没写理由
ANSWER_NO_SELECTION = "NO_LINE_SELECTED"           # 一行都没勾
ANSWER_NO_ITEMS = "NO_TRANSFER_ITEM"               # 单上没有可调的瓶


def check_parties(from_manager: str, to_manager: str) -> Optional[str]:
    """出料人与受益人能不能构成一笔调拨。返回原因码，``None`` = 没问题。"""
    from_manager = (from_manager or "").strip()
    to_manager = (to_manager or "").strip()
    if not from_manager or not to_manager:
        return ANSWER_EMPTY
    if from_manager == to_manager:
        return ANSWER_SELF
    return None


def can_answer(
    status: str, from_manager: str, me: str, is_super_admin: bool = False
) -> bool:
    """我能不能对这张单点头或拒绝。

    超管可以代点头（出料人休假、离职），但那是**代签**：业务层必须把
    ``forced`` 标上并写理由。代签与「审批超管不代办」不冲突——审批代签会
    把「谁批的」写错，而调拨代签只是把「谁同意」记成超管 + 备注，事实清楚。
    """
    if (status or "").strip() != TRANSFER_REQUESTED:
        return False
    if is_super_admin:
        return True
    me = (me or "").strip()
    return bool(me) and me == (from_manager or "").strip()


def answer_blocked_reason(
    status: str, from_manager: str, me: str, is_super_admin: bool = False
) -> str:
    """不能回答时返回一句能直接显示的话（空串 = 能回答）。"""
    if can_answer(status, from_manager, me, is_super_admin):
        return ""
    if (status or "").strip() != TRANSFER_REQUESTED:
        return f"这张单当前是「{status or '未知'}」，不是「待点头」，不能处理"
    return (
        f"调的是「{from_manager}」名下的保管权，只有他本人能点头；"
        "他休假请让超管代签（会记代签）"
    )


def can_cancel(
    status: str, requested_by: str, me: str, is_super_admin: bool = False
) -> bool:
    """发起人（或超管）能不能撤回一张还没被点头的单。"""
    if (status or "").strip() != TRANSFER_REQUESTED:
        return False
    if is_super_admin:
        return True
    me = (me or "").strip()
    return bool(me) and me == (requested_by or "").strip()


def can_reject(status: str, reason: str) -> Optional[str]:
    """拒绝的合法性。返回原因码，``None`` = 可以拒绝。

    拒绝必填理由——这一条**与 Q22（退回不写原因）相反**，因为两个动作对
    对方的意义不同：退回是「你的单有问题」，申请人自己知道哪有问题；拒绝
    调拨是「我不给」，对发起人是**可行动的信息**，他得改去找别人或走采购。
    """
    if (status or "").strip() != TRANSFER_REQUESTED:
        return ANSWER_NOT_REQUESTED
    if not (reason or "").strip():
        return ANSWER_REMARK_REQUIRED
    return None


def resolve_selections(
    total: int, selections: Optional[Iterable[int]]
) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    """把「勾了哪几行」拆成（同意的下标，不同意的下标）。

    ``selections=None`` 表示全同意；空集合表示一行都没勾——那是误操作，
    由调用方按 ``ANSWER_NO_SELECTION`` 拦掉。越界下标直接丢弃，不抛异常：
    页面下标来自上一次渲染，中途删行会差一位，抛异常只会让整单点不动。
    """
    if total <= 0:
        return (), ()
    if selections is None:
        return tuple(range(total)), ()
    chosen = {int(index) for index in selections if 0 <= int(index) < total}
    accepted = tuple(sorted(chosen))
    declined = tuple(index for index in range(total) if index not in chosen)
    return accepted, declined


def next_status(any_accepted: bool, any_pending: bool) -> str:
    """整单状态怎么定：有任何一行生效就是「已同意」，全拒才是「已拒绝」。"""
    if any_accepted:
        return TRANSFER_ACCEPTED
    if any_pending:
        return TRANSFER_REQUESTED
    return TRANSFER_REJECTED


def can_withdraw(status: str) -> bool:
    """这张单还能不能作废：只有已经生效或已拒绝的才不能。"""
    return (status or "").strip() in TRANSFER_OPEN_STATUSES


def describe(status: str, items: Sequence[object]) -> str:
    """一句话摘要，页面和日志共用（``items`` 只要有 ``lot_id`` 与 ``quantity``）。"""
    count = len(items)
    return f"{status}：{count} 瓶"


__all__ = [
    "ANSWER_EMPTY",
    "ANSWER_NOT_REQUESTED",
    "ANSWER_NOT_SUPPLIER",
    "ANSWER_NO_ITEMS",
    "ANSWER_NO_SELECTION",
    "ANSWER_REMARK_REQUIRED",
    "ANSWER_SELF",
    "ITEM_ACCEPTED",
    "ITEM_DECLINED",
    "ITEM_FAILED",
    "ITEM_PENDING",
    "ORIGIN_MANUAL",
    "ORIGIN_ORDER",
    "ORIGIN_SHEET",
    "REASON_FORCED",
    "REASON_MANUAL",
    "REASON_SHORTFALL",
    "TRANSFER_ACCEPTED",
    "TRANSFER_CANCELLED",
    "TRANSFER_DRAFT",
    "TRANSFER_OPEN_STATUSES",
    "TRANSFER_REJECTED",
    "TRANSFER_REQUESTED",
    "TRANSFER_STATUSES",
    "answer_blocked_reason",
    "can_answer",
    "can_cancel",
    "can_reject",
    "can_withdraw",
    "check_parties",
    "describe",
    "next_status",
    "resolve_selections",
]
