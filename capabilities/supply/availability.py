"""可用量评估：库存里那一堆瓶子，到底有多少是「现在真能拿来用的」。

用**过滤器组合**而不是一堆布尔参数，是因为规则会一直加：今天要排除
过期与已借出，明天要「距效期不足 30 天的不算」，后天要「管控品单人
限领 500 mL」。每加一条只写一个 :class:`LotFilter` 子类，已有规则与
调用方都不用改。

被排除的批次连同原因一起留在 :class:`Availability` 里——「为什么这瓶
不算」和「到底有多少」一样重要，否则盘点时无法解释差异。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping, Optional, Sequence

from domain.substance import SubstanceRef
from domain.units import Dimension, Quantity, Unit, parse_unit
from capabilities.supply.stock import ExpiryState, StockLot, StockSnapshot


# --------------------------------------------------------------------------
# 过滤器
# --------------------------------------------------------------------------


class LotFilter(ABC):
    """一条「这批算不算可用」的规则。"""

    #: 排除原因（写进报告，供盘点解释）
    reason: str = "不符合可用条件"

    @abstractmethod
    def accepts(self, lot: StockLot) -> bool:
        """返回 True 表示这批可以计入可用量。"""

    def describe(self) -> str:
        return self.reason


class HasQuantity(LotFilter):
    """有剩余量。"""

    reason = "无剩余量"

    def accepts(self, lot: StockLot) -> bool:
        return not lot.is_empty


class BorrowableOnly(LotFilter):
    """处于「可借」状态（未借出、未报废）。"""

    reason = "已借出或已报废"

    def accepts(self, lot: StockLot) -> bool:
        return lot.borrowable and not lot.scrapped


class NotExpired(LotFilter):
    """未过期；「待确认」按可用处理。"""

    reason = "已过期"

    def accepts(self, lot: StockLot) -> bool:
        return lot.expiry.is_usable


class WithinDays(LotFilter):
    """距效期至少还有若干天（避免用一用就过期）。"""

    def __init__(self, days: int) -> None:
        self.days = int(days)
        self.reason = f"距效期不足 {self.days} 天"

    def accepts(self, lot: StockLot) -> bool:
        if lot.expiry is ExpiryState.EXPIRED:
            return False
        remaining = lot.days_to_expiry
        if remaining is None:
            return True
        return remaining >= self.days


class ExcludeSubstance(LotFilter):
    """按物质排除（例如剧毒品不进入自动分配）。"""

    def __init__(self, keys: Iterable[str], reason: str = "按规则不参与自动分配") -> None:
        self._keys = set(keys)
        self.reason = reason

    def accepts(self, lot: StockLot) -> bool:
        return lot.substance.key not in self._keys


# --------------------------------------------------------------------------
# 排除记录与可用量
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExcludedLot:
    """一批被排除的库存，以及为什么。"""

    lot: StockLot
    reason: str

    def describe(self) -> str:
        return f"{self.lot.lot_id}（{self.lot.quantity.format(2)}）：{self.reason}"


@dataclass(frozen=True)
class Availability:
    """某时刻、某策略下的可用量结论。"""

    #: 物质引用键 → {量纲: 该量纲下的可用合计}
    balances: Mapping[str, Mapping[Dimension, Quantity]] = field(default_factory=dict)
    excluded: tuple[ExcludedLot, ...] = ()
    taken_at: datetime = field(default_factory=datetime.now)
    policy_label: str = ""

    # ---------------------------------------------------------------- 查询
    def of(self, ref: SubstanceRef, unit: Unit) -> Quantity:
        """某物质在指定单位下的可用量（无对应量纲则为零）。"""
        target = unit if isinstance(unit, Unit) else parse_unit(unit)
        by_dimension = self.balances.get(ref.key) or {}
        quantity = by_dimension.get(target.dimension)
        if quantity is None:
            return Quantity.zero(target)
        return quantity.to(target)

    def of_substance(self, substance) -> Quantity:
        """按物质自身默认单位取可用量（页面摘要用）。"""
        unit = substance.default_unit if hasattr(substance, "default_unit") else parse_unit("g")
        return self.of(substance.ref, unit)

    def any_of(self, key: str) -> Optional[Quantity]:
        """取该物质任意一个量纲下的可用量（跨量纲换算的起点）。"""
        by_dimension = self.balances.get(key) or {}
        for quantity in by_dimension.values():
            return quantity
        return None

    def dimensions_of(self, key: str) -> set[Dimension]:
        return set((self.balances.get(key) or {}).keys())

    def mapping_for(self, sheet) -> dict[str, Quantity]:
        """把可用量摊成「物质键 → 该需求行的单位」。

        需求单里同一物质可能既是质量需求又是体积需求（不太常见但要支持），
        所以按行取量纲，而不是按物质取一个数。
        """
        mapping: dict[str, Quantity] = {}
        for line in sheet.lines:
            unit = line.quantity.unit
            key = (line.key, unit.symbol)
            if key in mapping:
                continue
            mapping[line.key] = self.of(line.substance, unit)
        return mapping

    def total_excluded(self) -> int:
        return len(self.excluded)

    def excluded_reasons(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.excluded:
            counts[item.reason] = counts.get(item.reason, 0) + 1
        return counts

    def describe(self) -> str:
        kinds = len(self.balances)
        text = f"可用量：{kinds} 种物质"
        if self.excluded:
            reasons = "、".join(f"{k}×{v}" for k, v in self.excluded_reasons().items())
            text += f"；排除 {len(self.excluded)} 个批次（{reasons}）"
        return text


# --------------------------------------------------------------------------
# 策略
# --------------------------------------------------------------------------


class AvailabilityPolicy:
    """策略 = 一组过滤器的合取。

    自身也实现 ``accepts``，所以策略可以嵌套组合（标准策略 + 额外限制）。
    """

    def __init__(self, *filters: LotFilter, label: str = "标准可用量") -> None:
        self._filters: tuple[LotFilter, ...] = tuple(filters)
        self.label = label

    def accepts(self, lot: StockLot) -> bool:
        return all(lot_filter.accepts(lot) for lot_filter in self._filters)

    def rejection_reason(self, lot: StockLot) -> str:
        for lot_filter in self._filters:
            if not lot_filter.accepts(lot):
                return lot_filter.reason
        return ""

    def evaluate(self, snapshot: StockSnapshot) -> Availability:
        """按本策略把快照折算成可用量。"""
        balances: dict[str, dict[Dimension, Quantity]] = {}
        excluded: list[ExcludedLot] = []

        for lot in snapshot.lots:
            if not self.accepts(lot):
                excluded.append(ExcludedLot(lot, self.rejection_reason(lot)))
                continue
            key = lot.substance.key
            dimension = lot.quantity.unit.dimension
            bucket = balances.setdefault(key, {})
            existing = bucket.get(dimension)
            bucket[dimension] = (
                lot.quantity if existing is None else existing + lot.quantity
            )

        return Availability(
            balances=balances,
            excluded=tuple(excluded),
            taken_at=snapshot.taken_at,
            policy_label=self.label,
        )

    def with_extra(self, *filters: LotFilter) -> "AvailabilityPolicy":
        """在现有策略上追加规则（返回新策略，不修改原策略）。"""
        return AvailabilityPolicy(*self._filters, *filters, label=self.label)

    def describe(self) -> str:
        rules = "、".join(f.describe() for f in self._filters)
        return f"{self.label}（{rules}）"


def standard_policy() -> AvailabilityPolicy:
    """标准策略：有量、可借、未过期。"""
    return AvailabilityPolicy(
        HasQuantity(), BorrowableOnly(), NotExpired(), label="标准可用量"
    )


def strict_policy(shelf_life_buffer_days: int = 30) -> AvailabilityPolicy:
    """严格策略：在标准之上再要求距效期至少 N 天。"""
    return AvailabilityPolicy(
        HasQuantity(),
        BorrowableOnly(),
        NotExpired(),
        WithinDays(shelf_life_buffer_days),
        label=f"严格可用量（效期余量 {shelf_life_buffer_days} 天）",
    )


#: 模块级别名：业务层按名字取用，避免到处 new
StandardAvailabilityPolicy = standard_policy
StrictAvailabilityPolicy = strict_policy


__all__ = [
    "LotFilter",
    "HasQuantity",
    "BorrowableOnly",
    "NotExpired",
    "WithinDays",
    "ExcludeSubstance",
    "ExcludedLot",
    "Availability",
    "AvailabilityPolicy",
    "standard_policy",
    "strict_policy",
    "StandardAvailabilityPolicy",
    "StrictAvailabilityPolicy",
]
