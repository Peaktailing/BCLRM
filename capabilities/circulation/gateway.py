"""流转网关：需求单怎么变成「谁去拿、从哪拿、拿多少」。

BCLRM 原来有三层单据（需求单 → 调配单 → 领用工单），biomanager 走的是
另一套领用流。这个差异不该渗透到业务层，所以用网关抽象隔开：业务层只
说「把这张需求单提交、审批、发放、关闭」，具体落成几张表、叫什么名字，
由网关实现决定。

本轮先交付：抽象 + 内存实现（可直接跑通测试与演示）+ 明确的接入点说明。
接 BCLRM 原生单据体系时，只需实现一个 ``NativeCirculationGateway``，
业务层与计算逻辑零改动。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from itertools import count
from typing import Optional

from domain.requirement import RequirementSheet


class CirculationError(Exception):
    """流转环节的业务错误（状态不允许、越权审批等）。"""


class GatewayNotReady(CirculationError):
    """该网关尚未接通真实单据体系（阶段性边界，不是缺陷）。"""


class TicketStatus(str, Enum):
    """领用单据状态。"""

    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    ISSUED = "issued"
    CLOSED = "closed"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return {
            TicketStatus.SUBMITTED: "待审批",
            TicketStatus.APPROVED: "已批准",
            TicketStatus.REJECTED: "已驳回",
            TicketStatus.ISSUED: "已发放",
            TicketStatus.CLOSED: "已关闭",
            TicketStatus.CANCELLED: "已取消",
        }[self]

    def can_transition_to(self, target: "TicketStatus") -> bool:
        allowed = {
            TicketStatus.SUBMITTED: {TicketStatus.APPROVED, TicketStatus.REJECTED, TicketStatus.CANCELLED},
            TicketStatus.APPROVED: {TicketStatus.ISSUED, TicketStatus.CANCELLED},
            TicketStatus.ISSUED: {TicketStatus.CLOSED},
            TicketStatus.REJECTED: set(),
            TicketStatus.CLOSED: set(),
            TicketStatus.CANCELLED: set(),
        }
        return target in allowed[self]

    @property
    def is_open(self) -> bool:
        return self in (TicketStatus.SUBMITTED, TicketStatus.APPROVED, TicketStatus.ISSUED)


@dataclass(frozen=True)
class TicketEvent:
    """单据动作留痕。"""

    at: datetime
    actor: str
    action: str
    note: str = ""

    def describe(self) -> str:
        stamp = self.at.strftime("%Y-%m-%d %H:%M")
        return f"{stamp} {self.actor} {self.action}" + (f"（{self.note}）" if self.note else "")


@dataclass(frozen=True)
class DemandTicket:
    """一张领用单据（不可变，状态变化返回新对象）。"""

    ticket_no: str
    sheet: RequirementSheet
    requester: str
    status: TicketStatus = TicketStatus.SUBMITTED
    created_at: datetime = field(default_factory=datetime.now)
    assignee: str = ""
    note: str = ""
    events: tuple[TicketEvent, ...] = ()

    @property
    def line_count(self) -> int:
        return len(self.sheet.lines)

    @property
    def is_open(self) -> bool:
        return self.status.is_open

    def with_status(
        self,
        status: TicketStatus,
        actor: str,
        action: str,
        note: str = "",
    ) -> "DemandTicket":
        if not self.status.can_transition_to(status):
            raise CirculationError(
                f"单据 {self.ticket_no} 不能从「{self.status.label}」变为「{status.label}」"
            )
        event = TicketEvent(datetime.now(), actor, action, note)
        return replace(self, status=status, events=self.events + (event,))

    def describe(self) -> str:
        return (
            f"{self.ticket_no} · {self.sheet.title} · {self.sheet.scale.describe()} · "
            f"{self.line_count} 项 · {self.status.label} · 申请人 {self.requester}"
        )


class CirculationGateway(ABC):
    """流转网关抽象。"""

    # ---------------------------------------------------------------- 动作
    @abstractmethod
    def submit(self, sheet: RequirementSheet, requester: str, note: str = "") -> DemandTicket:
        """提交需求单，生成待审批单据。"""

    @abstractmethod
    def approve(self, ticket_no: str, approver: str, note: str = "") -> DemandTicket:
        """审批通过。"""

    @abstractmethod
    def reject(self, ticket_no: str, approver: str, reason: str = "") -> DemandTicket:
        """驳回。"""

    @abstractmethod
    def issue(self, ticket_no: str, operator: str, note: str = "") -> DemandTicket:
        """按单发放（对应 BCLRM 的领用工单 / 出库）。"""

    @abstractmethod
    def close(self, ticket_no: str, operator: str, note: str = "") -> DemandTicket:
        """关闭单据（归还或结案后）。"""

    # ---------------------------------------------------------------- 查询
    @abstractmethod
    def get(self, ticket_no: str) -> DemandTicket:
        """取单据；不存在抛 :class:`CirculationError`。"""

    @abstractmethod
    def open_tickets(self) -> tuple[DemandTicket, ...]:
        """所有未完结单据。"""

    # ---------------------------------------------------------------- 通用规则
    @staticmethod
    def _guard_self_approval(ticket: DemandTicket, approver: str) -> None:
        """申请人不得自审。审批权是控制点，不是手续。"""
        if approver and ticket.requester and approver.strip() == ticket.requester.strip():
            raise CirculationError(f"申请人 {approver} 不能审批自己的单据 {ticket.ticket_no}")


class InMemoryCirculationGateway(CirculationGateway):
    """内存实现：跑测试、做演示、或作为「还没接数据库」时的默认网关。"""

    def __init__(self, prefix: str = "REQ") -> None:
        self._tickets: dict[str, DemandTicket] = {}
        self._seq = count(1)
        self._prefix = prefix

    # ---------------------------------------------------------------- 动作
    def submit(self, sheet: RequirementSheet, requester: str, note: str = "") -> DemandTicket:
        if not (requester or "").strip():
            raise CirculationError("申请人不能为空")
        if not sheet.lines:
            raise CirculationError("需求单没有明细，不能提交")
        ticket_no = f"{self._prefix}{datetime.now():%Y%m%d}-{next(self._seq):04d}"
        ticket = DemandTicket(
            ticket_no=ticket_no,
            sheet=sheet,
            requester=requester.strip(),
            note=note,
            events=(TicketEvent(datetime.now(), requester.strip(), "提交"),),
        )
        self._tickets[ticket_no] = ticket
        return ticket

    def approve(self, ticket_no: str, approver: str, note: str = "") -> DemandTicket:
        ticket = self.get(ticket_no)
        self._guard_self_approval(ticket, approver)
        updated = ticket.with_status(TicketStatus.APPROVED, approver, "审批通过", note)
        self._tickets[ticket_no] = updated
        return updated

    def reject(self, ticket_no: str, approver: str, reason: str = "") -> DemandTicket:
        ticket = self.get(ticket_no)
        self._guard_self_approval(ticket, approver)
        updated = ticket.with_status(TicketStatus.REJECTED, approver, "驳回", reason)
        self._tickets[ticket_no] = updated
        return updated

    def issue(self, ticket_no: str, operator: str, note: str = "") -> DemandTicket:
        ticket = self.get(ticket_no)
        updated = ticket.with_status(TicketStatus.ISSUED, operator, "发放", note)
        self._tickets[ticket_no] = updated
        return updated

    def close(self, ticket_no: str, operator: str, note: str = "") -> DemandTicket:
        ticket = self.get(ticket_no)
        updated = ticket.with_status(TicketStatus.CLOSED, operator, "关闭", note)
        self._tickets[ticket_no] = updated
        return updated

    # ---------------------------------------------------------------- 查询
    def get(self, ticket_no: str) -> DemandTicket:
        ticket = self._tickets.get(ticket_no)
        if ticket is None:
            raise CirculationError(f"单据不存在：{ticket_no}")
        return ticket

    def open_tickets(self) -> tuple[DemandTicket, ...]:
        return tuple(t for t in self._tickets.values() if t.is_open)

    def all_tickets(self) -> tuple[DemandTicket, ...]:
        return tuple(self._tickets.values())


__all__ = [
    "CirculationError",
    "GatewayNotReady",
    "TicketStatus",
    "TicketEvent",
    "DemandTicket",
    "CirculationGateway",
    "InMemoryCirculationGateway",
]
