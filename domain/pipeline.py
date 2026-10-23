"""两段管线：教师申领与管理员调配是同一条链上的前后两段。

过去把「需求单」当成一张能自查自足的凭证，于是想当然地给它配一套
「提交 → 审批 → 发放」的状态机。但只要承认保管权的存在，就会看到真实
流程是这样的：

    ┌── 第一段：承接 ─────────────────────────────┐
    │ 教师：这节实验课缺 A、B、C                    │
    │   → 找**这门课对应的管理员**（指派，不是遴选） │
    │   → 他只报自己名下够不够                       │
    │   → 够：实物出库，**保管权不变**（教师不是所有人）│
    │   → 不够：把差额交出来                          │
    └───────────────────┬─────────────────────────┘
                        │ 差额是唯一合法的传递物
    ┌───────────────────▼─────────────────────────┐
    │ 第二段：平账                                 │
    │ 缺料的管理员：去别的管理员名下调               │
    │   → **保管权流转**（从 B 名下转到 A 名下）      │
    │   → 全院都调不到：转采购                        │
    └─────────────────────────────────────────────┘

两段的产出物性质不同，因此不能是同一种票据的两个状态：

===========  ==========================  ==========================
            第一段 · 承接               第二段 · 平账
===========  ==========================  ==========================
申报人       教师                        缺料的管理员
受理人       该课/项目的对应管理员        其他管理员（可能多个）
对库存的影响  实物减少，保管权不变          保管权转移，实物不动
对应单据     borrow_order（领用）          allocation_order（调配）
前置约束     无                          requester 必须是管理员
===========  ==========================  ==========================

``Acceptance.shortfall_sheet()`` 就是那个「唯一合法的传递物」：缺口不是
另起一张单，而是原需求单的一个子集。这样一张申请从教师提出到料配齐，
始终是同一条线，不会断成两笔互不相干的账。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Iterator, Optional

from domain.batch import BatchScale
from domain.custody import Custodian
from domain.recipe import SourceRef
from domain.requirement import RequirementLine, RequirementSheet
from domain.substance import SubstanceRef
from domain.units import Quantity


class Stage(str, Enum):
    """管线上的两段。"""

    INTAKE = "intake"          # 第一段：教师申请 → 受理管理员承接
    REBALANCE = "rebalance"    # 第二段：受理管理员 → 其他管理员平账

    @property
    def label(self) -> str:
        return {
            Stage.INTAKE: "承接",
            Stage.REBALANCE: "平账",
        }[self]

    @property
    def actor_role(self) -> str:
        """这一段里「谁在提要求」。"""
        return {
            Stage.INTAKE: "任课教师",
            Stage.REBALANCE: "受理管理员",
        }[self]


class PipelineError(ValueError):
    """管线环节的业务错误。"""


# ============================================================================
# 第一段
# ============================================================================


@dataclass(frozen=True)
class TeacherRequest:
    """第一段的输入：教师为某次教学/科研活动提出的备料申请。

    与 :class:`~domain.requirement.RequirementSheet` 的分工：需求单回答
    「算出来要多少」，申请回答「谁、为哪件事、什么时候要」。路由受理人
    靠的是 ``source``（课程/项目），不是需求单里的配方名——同一个配方在
    两门课里用，受理人可能不同。
    """

    requester: str
    sheet: RequirementSheet
    source: Optional[SourceRef] = None
    due_hint: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not (self.requester or "").strip():
            raise PipelineError("申请人不能为空")
        if not self.sheet.lines:
            raise PipelineError("申请没有明细，不能受理")

    @property
    def requester_name(self) -> str:
        return self.requester.strip()

    @property
    def source_code(self) -> str:
        return self.source.code if self.source else ""

    def describe(self) -> str:
        where = f"（{self.source.title}）" if self.source and self.source.title else ""
        due = f"，{self.due_hint}用" if self.due_hint else ""
        return (
            f"{self.requester_name} 为 {self.sheet.title}{where} 申请 "
            f"{len(self.sheet.lines)} 项备料{due}"
        )

    def to_record(self) -> dict:
        return {
            "requester": self.requester_name,
            "recipe_key": self.sheet.recipe_key,
            "title": self.sheet.title,
            "source_kind": self.source.kind.value if self.source else None,
            "source_code": self.source.code if self.source else None,
            "source_title": self.source.title if self.source else None,
            "due_hint": self.due_hint,
            "note": self.note,
        }


@dataclass(frozen=True)
class IssueLine:
    """第一段承诺发放的一行。

    **保管权不变**：料到教师手上用，用不完还回来，账面上它一直归受理
    管理员。所以这里只有「哪瓶、发多少」，没有「转给谁」。
    """

    substance: SubstanceRef
    quantity: Quantity
    lot_id: str = ""
    note: str = ""
    seq: int = 0

    @property
    def name(self) -> str:
        return self.substance.name or self.substance.key

    def describe(self) -> str:
        lot = f"（{self.lot_id}）" if self.lot_id else ""
        return f"{self.name} {self.quantity.format(3)}{lot}"

    def to_record(self) -> dict:
        return {
            "seq": self.seq,
            "substance_key": self.substance.key,
            "display_name": self.substance.name,
            "cas_number": self.substance.cas.value if self.substance.cas else None,
            "quantity": self.quantity.to_float(),
            "unit": self.quantity.unit.symbol,
            "lot_id": self.lot_id,
            "note": self.note,
        }


@dataclass(frozen=True)
class Shortfall:
    """承接后仍缺的一行——这是两段之间唯一被允许传递的东西。

    保留 ``requirement`` 原始行，是为了能把缺口还原成一张同构的需求单：
    序号、角色、管控标记、计量依据全部继承，第二段拿到的不是「一堆数字」，
    而是一张能直接下给别的管理员的单子。
    """

    requirement: RequirementLine
    quantity: Quantity
    reason: str = ""

    # ---- 数量校验：允许零，不允许负（负数是算法错误的信号，不是业务状态）
    def __post_init__(self) -> None:
        if self.quantity.is_negative():
            raise PipelineError(f"{self.requirement.name} 的缺口不能为负")

    @property
    def substance(self) -> SubstanceRef:
        return self.requirement.substance

    @property
    def name(self) -> str:
        return self.requirement.name

    @property
    def is_empty(self) -> bool:
        return self.quantity.is_zero()

    @property
    def is_controlled(self) -> bool:
        return self.requirement.controlled

    def describe(self) -> str:
        text = f"{self.name} 缺 {self.quantity.format(3)}"
        return f"{text}（{self.reason}）" if self.reason else text

    def with_quantity(self, quantity: Quantity) -> "Shortfall":
        return replace(self, quantity=quantity)


@dataclass(frozen=True)
class LotPick:
    """从某一瓶上取走的量（批次分配结果）。"""

    lot_id: str
    quantity: Quantity

    def describe(self) -> str:
        return f"{self.lot_id} 取 {self.quantity.format(3)}"


@dataclass(frozen=True)
class Acceptance:
    """第一段的产出：受理结论。

    核心不变量——**::

        Σ issued + Σ shortfalls ≡ 原始需求

    料不许凭空消失。这条不变量让「教师申请了 10 g，最后只到了 6 g，那 4 g
    去哪了」这类问题永远有答案：要么在 issued 里，要么在 shortfalls 里，
    要么在原始需求里对不上（那就是算错了，测试会拦）。
    """

    custodian: Custodian
    request: TeacherRequest
    issued: tuple[IssueLine, ...] = ()
    shortfalls: tuple[Shortfall, ...] = ()
    stage: Stage = Stage.INTAKE
    decided_at: datetime = field(default_factory=datetime.now)
    notes: tuple[str, ...] = ()

    # ---------------------------------------------------------------- 视图
    def __iter__(self) -> Iterator[IssueLine]:
        return iter(self.issued)

    @property
    def is_complete(self) -> bool:
        """名下就够，不需要第二段。"""
        return not self.shortfalls

    @property
    def is_empty(self) -> bool:
        """一项都没发出去（名下完全没有）。"""
        return not self.issued

    @property
    def shortfall_count(self) -> int:
        return len(self.shortfalls)

    @property
    def issued_total_by_unit(self) -> dict[str, Quantity]:
        """按单位汇总实发量（页面摘要用；不同量纲不合并）。"""
        totals: dict[str, Quantity] = {}
        for line in self.issued:
            unit = line.quantity.unit.symbol
            totals[unit] = totals.get(unit, Quantity.zero(line.quantity.unit)) + line.quantity
        return totals

    def shortfall_of(self, ref: SubstanceRef) -> Optional[Shortfall]:
        for item in self.shortfalls:
            if item.substance.key == ref.key:
                return item
        return None

    # ---------------------------------------------------------------- 传递
    def shortfall_sheet(self) -> Optional[RequirementSheet]:
        """把缺口还原成一张需求单，交给第二段。

        返回 ``None`` 表示不需要第二段。这张单子的 ``recipe_key`` 加 ``:gap``
        后缀，好在日志与审计里一眼认出它是承接后的残量，而不是原始配方。
        """
        if not self.shortfalls:
            return None
        lines = tuple(
            item.requirement.with_quantity(item.quantity)
            for item in self.shortfalls
            if not item.is_empty
        )
        if not lines:
            return None
        sheet = self.request.sheet
        return RequirementSheet(
            recipe_key=f"{sheet.recipe_key}:gap",
            title=f"{sheet.title}（缺口）",
            scale=sheet.scale,
            lines=lines,
            source=sheet.source,
            warnings=(f"承接人 {self.custodian.describe()} 名下不足",),
        )

    # ---------------------------------------------------------------- 摘要
    def describe(self) -> str:
        head = (
            f"{self.custodian.describe()} 受理 {self.request.requester_name} 的申请"
            f"（{self.request.sheet.title}）"
        )
        if self.is_complete:
            return f"{head}：名下可满足，实发 {len(self.issued)} 项"
        return (
            f"{head}：实发 {len(self.issued)} 项，"
            f"缺 {len(self.shortfalls)} 项需向其他管理员调配"
        )

    def explain(self) -> list[str]:
        rows = [f"[{self.stage.label}] {self.custodian.describe()} 受理"]
        rows.extend(f"  发 → {line.describe()}" for line in self.issued)
        rows.extend(f"  缺 → {item.describe()}" for item in self.shortfalls)
        return rows

    def to_record(self) -> dict:
        return {
            "stage": self.stage.value,
            "custodian": self.custodian.name,
            "custodian_department": self.custodian.department,
            "requester": self.request.requester_name,
            "recipe_key": self.request.sheet.recipe_key,
            "title": self.request.sheet.title,
            "decided_at": self.decided_at.isoformat(timespec="seconds"),
            "issued": [line.to_record() for line in self.issued],
            "shortfalls": [
                {
                    "substance_key": item.substance.key,
                    "display_name": item.name,
                    "quantity": item.quantity.to_float(),
                    "unit": item.quantity.unit.symbol,
                    "reason": item.reason,
                }
                for item in self.shortfalls
            ],
        }


# ============================================================================
# 第二段
# ============================================================================


@dataclass(frozen=True)
class TransferLine:
    """一笔调拨：从某保管人名下转到受理人名下。

    这里才有「转给谁」——因为这一段动的正是**保管权**。第一段的
    :class:`IssueLine` 刻意没有这个字段，就是这个道理。
    """

    from_custodian: Custodian
    to_custodian: Custodian
    substance: SubstanceRef
    quantity: Quantity
    lot_id: str = ""
    priority: int = 0
    note: str = ""

    @property
    def name(self) -> str:
        return self.substance.name or self.substance.key

    @property
    def is_cross_department(self) -> bool:
        return not self.from_custodian.in_department_of(self.to_custodian)

    def describe(self) -> str:
        span = "跨科室" if self.is_cross_department else "同科室"
        return (
            f"{self.from_custodian.name} → {self.to_custodian.name}："
            f"{self.name} {self.quantity.format(3)}（{span}）"
        )

    def to_record(self) -> dict:
        return {
            "from_custodian": self.from_custodian.name,
            "to_custodian": self.to_custodian.name,
            "substance_key": self.substance.key,
            "display_name": self.substance.name,
            "cas_number": self.substance.cas.value if self.substance.cas else None,
            "quantity": self.quantity.to_float(),
            "unit": self.quantity.unit.symbol,
            "lot_id": self.lot_id,
            "is_cross_department": self.is_cross_department,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class TransferProposal:
    """第二段的产出：调拨建议。

    只是**建议**——真正动保管权要管理员点确认（那是 ``manager_service``
    的 ``transfer``）。中台算清楚「从谁那调多少」，业务层负责落单与留痕。
    """

    beneficiary: Custodian
    lines: tuple[TransferLine, ...] = ()
    unresolved: tuple[Shortfall, ...] = ()
    stage: Stage = Stage.REBALANCE
    planned_at: datetime = field(default_factory=datetime.now)

    def __iter__(self) -> Iterator[TransferLine]:
        return iter(self.lines)

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def is_resolved(self) -> bool:
        """全部缺口都能靠调拨平掉（不需采购）。"""
        return not self.unresolved

    def suppliers(self) -> tuple[Custodian, ...]:
        seen: dict[str, Custodian] = {}
        for line in self.lines:
            seen.setdefault(line.from_custodian.key, line.from_custodian)
        return tuple(seen[key] for key in sorted(seen))

    def total_of(self, ref: SubstanceRef, unit) -> Quantity:
        total = Quantity.zero(unit)
        for line in self.lines:
            if line.substance.key != ref.key:
                continue
            if line.quantity.unit.dimension is not unit.dimension:
                continue
            total = total + line.quantity.to(unit)
        return total

    def purchase_sheet(self) -> Optional[RequirementSheet]:
        """调拨也解决不了的部分，转成采购需求单。"""
        lines = tuple(
            item.requirement.with_quantity(item.quantity)
            for item in self.unresolved
            if not item.is_empty
        )
        if not lines:
            return None
        first = self.lines[0] if self.lines else None
        return RequirementSheet(
            recipe_key="purchase:shortfall",
            title=f"{self.beneficiary.name} 的缺口转采购",
            scale=BatchScale.single(),
            lines=lines,
            warnings=(
                f"受理人 {self.beneficiary.name} 名下与全院可调量均不足"
                + (f"；已从 {first.from_custodian.name} 等处调拨部分" if first else ""),
            ),
        )

    def describe(self) -> str:
        if not self.lines and not self.unresolved:
            return "无缺口，无需调配"
        head = (
            f"为 {self.beneficiary.name} 平账：{len(self.lines)} 笔调拨，"
            f"涉及 {len(self.suppliers())} 名管理员"
        )
        if self.unresolved:
            head += f"；仍有 {len(self.unresolved)} 项需采购"
        return head

    def explain(self) -> list[str]:
        rows = [f"[{self.stage.label}] {self.beneficiary.describe()} 的缺口处理"]
        rows.extend(f"  调 → {line.describe()}" for line in self.lines)
        rows.extend(f"  购 → {item.describe()}" for item in self.unresolved)
        if not self.lines and not self.unresolved:
            rows.append("  （无缺口）")
        return rows

    def to_record(self) -> dict:
        return {
            "stage": self.stage.value,
            "beneficiary": self.beneficiary.name,
            "planned_at": self.planned_at.isoformat(timespec="seconds"),
            "transfers": [line.to_record() for line in self.lines],
            "unresolved": [
                {
                    "substance_key": item.substance.key,
                    "display_name": item.name,
                    "quantity": item.quantity.to_float(),
                    "unit": item.quantity.unit.symbol,
                    "reason": item.reason,
                }
                for item in self.unresolved
            ],
        }


# ============================================================================
# 整条线
# ============================================================================


@dataclass(frozen=True)
class PipelineResult:
    """一条申请走完两段之后的完整结果。

    ``trace`` 是给老师看的：他知道自己该找谁、谁手上不够、最后从谁那调的。
    这事在 BCLRM 原来是黑箱——教师只看到「已审批」，不知道料是从隔壁
    教研室借来的。
    """

    request: TeacherRequest
    acceptance: Acceptance
    proposal: Optional[TransferProposal] = None
    trace: tuple[str, ...] = ()

    @property
    def custodian(self) -> Custodian:
        return self.acceptance.custodian

    @property
    def is_fulfilled(self) -> bool:
        """名下 + 调拨 --- 全部满足（不含需采购的部分）。"""
        if self.acceptance.is_complete:
            return True
        return self.proposal is not None and self.proposal.is_resolved

    @property
    def needs_purchase(self) -> bool:
        return self.proposal is not None and bool(self.proposal.unresolved)

    @property
    def purchase_sheet(self) -> Optional[RequirementSheet]:
        return self.proposal.purchase_sheet() if self.proposal else None

    def describe(self) -> str:
        bits = [self.acceptance.describe()]
        if self.proposal is not None:
            bits.append(self.proposal.describe())
        if self.needs_purchase:
            bits.append("部分需转采购")
        return "；".join(bits)

    def to_record(self) -> dict:
        return {
            "request": self.request.to_record(),
            "acceptance": self.acceptance.to_record(),
            "proposal": self.proposal.to_record() if self.proposal else None,
            "trace": list(self.trace),
            "is_fulfilled": self.is_fulfilled,
            "needs_purchase": self.needs_purchase,
        }


__all__ = [
    "Stage",
    "PipelineError",
    "TeacherRequest",
    "IssueLine",
    "Shortfall",
    "LotPick",
    "Acceptance",
    "TransferLine",
    "TransferProposal",
    "PipelineResult",
]
