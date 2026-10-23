"""保管账：把全库快照按「谁名下」切开。

中台 supply 的 ``StockSnapshot`` 回答「学校总共有多少」，这对采购与总账
是对的；但两段管线每一步问的都是另一个问题：

- 第一段：**受理管理员名下**有多少（决定他自己发多少、缺多少）
- 第二段：**其他管理员名下**分别有多少（决定从谁那调）

所以这里不做新的计量，只是把同一份快照换个切法。切完仍交给
``SupplyEvaluator`` 评估——跨量纲换算、过期过滤、管控规则全部复用，
一分钱逻辑都不重写。

**未指定保管人的批次不进入任何一段。** 没人认领的瓶不能借，也不能被
调拨——它先得有人认领。这类批次单列出来提示，否则会出现「明明账上
有 500 mL 却谁也调不到」的悬空账。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterable, Optional

from capabilities.supply.availability import AvailabilityPolicy, standard_policy
from capabilities.supply.stock import StockLot, StockSnapshot
from domain.custody import Custodian, Holding, Holdings
from domain.substance import SubstanceRef


class CustodyLedger(ABC):
    """保管账抽象。"""

    # ---------------------------------------------------------------- 原始
    @abstractmethod
    def snapshot(self) -> StockSnapshot:
        """全库快照（未过滤）。"""

    @abstractmethod
    def custodians(self) -> tuple[Custodian, ...]:
        """账上出现过的保管人（不含"未指定"）。"""

    # ---------------------------------------------------------------- 切分
    @abstractmethod
    def subset(self, custodian: Custodian) -> StockSnapshot:
        """只含该保管人名下批次的快照。"""

    @abstractmethod
    def others(self, custodian: Custodian) -> StockSnapshot:
        """排除该保管人后的快照（第二段撮合用）。"""

    def lots(self, custodian: Custodian, ref: SubstanceRef) -> tuple[StockLot, ...]:
        """该保管人名下某物质的可用批次（不含未认领）。"""
        return tuple(
            lot
            for lot in self.subset(custodian)
            if lot.substance.key == ref.key
        )

    @abstractmethod
    def unclaimed(self) -> StockSnapshot:
        """未指定保管人的快照（需先认领才能进入流转）。"""

    # ---------------------------------------------------------------- 摘要
    @abstractmethod
    def holdings(self) -> Holdings:
        """按保管人聚合的持有视图（页面展示用）。"""

    def describe(self) -> str:
        return (
            f"{len(self.custodians())} 名保管人 · "
            f"{len(self.snapshot())} 个可用批次 · "
            f"{len(self.unclaimed())} 个未指定保管人"
        )


class SnapshotLedger(CustodyLedger):
    """基于库存快照的保管账。

    ``policy`` 决定哪些批次算「可用」——过期、已借出、已报废的批次不该
    出现在任何人的名下，否则第一段会把它们承诺出去。
    """

    def __init__(
        self,
        snapshot: StockSnapshot,
        policy: Optional[AvailabilityPolicy] = None,
        department_of: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._policy = policy or standard_policy()
        self._department_of = department_of
        # 只保留策略认可的批次，一次过滤，后续所有切分都在这个集合上进行
        self._usable: tuple[StockLot, ...] = tuple(
            lot for lot in snapshot if self._policy.accepts(lot)
        )
        self._snapshot = StockSnapshot.of(self._usable, label=snapshot.label)

    # ---------------------------------------------------------------- 原始
    def snapshot(self) -> StockSnapshot:
        return self._snapshot

    def custodians(self) -> tuple[Custodian, ...]:
        seen: dict[str, Custodian] = {}
        for lot in self._usable:
            name = (lot.custodian or "").strip()
            if not name:
                continue
            seen.setdefault(name, self._custodian(name))
        return tuple(seen[key] for key in sorted(seen))

    # ---------------------------------------------------------------- 构造
    def _custodian(self, name: str) -> Custodian:
        department = ""
        if self._department_of is not None:
            department = self._department_of(name) or ""
        return Custodian(name=name, department=department)

    # ---------------------------------------------------------------- 切分
    def subset(self, custodian: Custodian) -> StockSnapshot:
        if custodian.is_anonymous:
            return StockSnapshot.of((), label="未指定保管人")
        return StockSnapshot.of(
            (lot for lot in self._usable if lot.custodian.strip() == custodian.key),
            label=f"{custodian.name} 名下",
        )

    def others(self, custodian: Custodian) -> StockSnapshot:
        return StockSnapshot.of(
            (
                lot
                for lot in self._usable
                if lot.custodian.strip() and lot.custodian.strip() != custodian.key
            ),
            label=f"除 {custodian.name} 外全院可调",
        )

    def unclaimed(self) -> StockSnapshot:
        return StockSnapshot.of(
            (lot for lot in self._usable if not lot.custodian.strip()),
            label="未指定保管人",
        )

    # ---------------------------------------------------------------- 摘要
    def holdings(self) -> Holdings:
        buckets: dict[tuple[str, str, str], Holding] = {}
        for lot in self._usable:
            name = (lot.custodian or "").strip()
            if not name:
                continue
            key = (name, lot.substance.key, lot.quantity.unit.symbol)
            existing = buckets.get(key)
            if existing is None:
                buckets[key] = Holding(
                    custodian=self._custodian(name),
                    substance=lot.substance,
                    quantity=lot.quantity,
                    lot_count=1,
                )
            else:
                buckets[key] = Holding(
                    custodian=existing.custodian,
                    substance=existing.substance,
                    quantity=existing.quantity + lot.quantity,
                    lot_count=existing.lot_count + 1,
                )
        ordered = tuple(
            sorted(
                buckets.values(),
                key=lambda h: (h.custodian.key, h.substance.name or h.substance.key),
            )
        )
        return Holdings(holdings=ordered)


class EmptyLedger(CustodyLedger):
    """空账（未接库存时的默认实现，让上层代码不必判空）。"""

    def snapshot(self) -> StockSnapshot:
        return StockSnapshot.of((), label="空库存")

    def custodians(self) -> tuple[Custodian, ...]:
        return ()

    def subset(self, custodian: Custodian) -> StockSnapshot:
        return self.snapshot()

    def others(self, custodian: Custodian) -> StockSnapshot:
        return self.snapshot()

    def unclaimed(self) -> StockSnapshot:
        return self.snapshot()

    def holdings(self) -> Holdings:
        return Holdings()


def ledger_of(
    lots: Iterable[StockLot],
    policy: Optional[AvailabilityPolicy] = None,
    department_of: Optional[Callable[[str], str]] = None,
    label: str = "",
) -> SnapshotLedger:
    """便捷构造：一堆批次 → 保管账。"""
    return SnapshotLedger(
        StockSnapshot.of(lots, label=label),
        policy=policy,
        department_of=department_of,
    )


__all__ = [
    "CustodyLedger",
    "SnapshotLedger",
    "EmptyLedger",
    "ledger_of",
]
