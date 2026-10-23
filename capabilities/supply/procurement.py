"""采购建议：缺口 → 该买几包、大概多少钱。

采购不是「缺口多少就买多少」：试剂按包装卖（500 mL/瓶、25 kg/袋），
买 120 mL 也得买一瓶 500 mL。这里把「缺口」与「包装规格」对上的事
收进一个规划器，业务层只管拿结论。

包装来源用 :class:`PackCatalog` 抽象——今天从历史采购单价推，明天从
供应商目录取，后天手工维护，规划器不用改。
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Sequence

from domain.requirement import CoverageLine, CoverageReport
from domain.substance import SubstanceRef
from domain.units import Dimension, Quantity, UnitError, parse_unit


@dataclass(frozen=True)
class PackSpec:
    """一种可采购的包装规格。"""

    substance_key: str
    pack_size: Quantity
    supplier: str = ""
    unit_price: Optional[Decimal] = None      # 每包单价（不是每克单价）
    lead_time_days: int = 0
    note: str = ""

    def __post_init__(self) -> None:
        if self.pack_size.base_value() <= 0:
            raise ValueError("包装规格必须为正")

    @property
    def unit_cost_per_base(self) -> Optional[Decimal]:
        """折合到基准单位（g / mL）的单价，用于跨规格比价。"""
        if self.unit_price is None:
            return None
        return self.unit_price / self.pack_size.base_value()

    def describe(self) -> str:
        bits = [self.pack_size.format(2)]
        if self.supplier:
            bits.append(self.supplier)
        if self.unit_price is not None:
            bits.append(f"¥{self.unit_price.normalize():f}/包")
        return " · ".join(bits)


class PackCatalog(ABC):
    """包装规格目录。"""

    @abstractmethod
    def packs_for(self, ref: SubstanceRef) -> tuple[PackSpec, ...]:
        """某物质的候选包装（按规格从小到大）。"""


class StaticPackCatalog(PackCatalog):
    """内存目录：便于测试，也作为「手工维护包装」的落点。"""

    def __init__(self, packs: Optional[Mapping[str, Sequence[PackSpec]]] = None) -> None:
        self._packs: dict[str, list[PackSpec]] = {
            key: sorted(items, key=lambda p: p.pack_size.base_value())
            for key, items in (packs or {}).items()
        }

    def packs_for(self, ref: SubstanceRef) -> tuple[PackSpec, ...]:
        return tuple(self._packs.get(ref.key, ()))

    def add(self, pack: PackSpec) -> None:
        bucket = self._packs.setdefault(pack.substance_key, [])
        bucket.append(pack)
        bucket.sort(key=lambda p: p.pack_size.base_value())

    def __len__(self) -> int:
        return sum(len(items) for items in self._packs.values())


@dataclass(frozen=True)
class PurchaseProposalLine:
    """一条采购建议。"""

    coverage: CoverageLine
    gap: Quantity
    pack: Optional[PackSpec] = None
    packs: int = 0
    order_quantity: Optional[Quantity] = None
    estimated_cost: Optional[Decimal] = None
    note: str = ""

    @property
    def name(self) -> str:
        return self.coverage.requirement.name

    @property
    def is_priced(self) -> bool:
        return self.pack is not None and self.estimated_cost is not None

    def describe(self) -> str:
        if self.pack is None:
            return f"{self.name}：缺 {self.gap.format(2)}，无包装规格，需询价"
        order = self.order_quantity.format(2) if self.order_quantity else self.gap.format(2)
        cost = f"，约 ¥{self.estimated_cost.normalize():f}" if self.estimated_cost is not None else ""
        return f"{self.name}：缺 {self.gap.format(2)} → 买 {self.packs} × {self.pack.pack_size.format(2)}（{order}{cost}）"


@dataclass(frozen=True)
class PurchaseProposal:
    """采购建议书。"""

    lines: tuple[PurchaseProposalLine, ...] = ()
    catalog_note: str = ""

    def __len__(self) -> int:
        return len(self.lines)

    def __iter__(self):
        return iter(self.lines)

    @property
    def estimated_cost(self) -> Decimal:
        return sum(
            (line.estimated_cost for line in self.lines if line.estimated_cost is not None),
            Decimal("0"),
        )

    @property
    def unpriced_lines(self) -> tuple[PurchaseProposalLine, ...]:
        return tuple(line for line in self.lines if line.pack is None)

    @property
    def total_quantity(self) -> dict[str, Quantity]:
        """按量纲汇总的采购总量。"""
        totals: dict[str, Quantity] = {}
        for line in self.lines:
            if line.order_quantity is None:
                continue
            dimension = line.order_quantity.unit.dimension.label
            existing = totals.get(dimension)
            totals[dimension] = (
                line.order_quantity if existing is None else existing + line.order_quantity
            )
        return totals

    def summary(self) -> str:
        if not self.lines:
            return "无需采购"
        text = f"{len(self.lines)} 项待采购，合计约 ¥{self.estimated_cost.normalize():f}"
        if self.unpriced_lines:
            text += f"（其中 {len(self.unpriced_lines)} 项无包装规格，未计价）"
        return text

    def describe(self) -> list[str]:
        return [line.describe() for line in self.lines]


class ProcurementPlanner:
    """缺口 → 采购建议。"""

    def __init__(self, catalog: PackCatalog) -> None:
        self._catalog = catalog

    def plan(self, coverage: CoverageReport) -> PurchaseProposal:
        lines: list[PurchaseProposalLine] = []
        for item in coverage.shortages:
            gap = item.gap
            if gap.is_zero():
                continue
            packs = self._catalog.packs_for(item.requirement.substance)
            chosen = self._choose_pack(packs, gap)
            if chosen is None:
                lines.append(
                    PurchaseProposalLine(
                        coverage=item,
                        gap=gap,
                        note="目录中没有该物质的包装规格，按缺口数量询价",
                    )
                )
                continue
            count = self._packs_needed(chosen.pack_size, gap)
            order_quantity = chosen.pack_size * Decimal(count)
            cost = (
                chosen.unit_price * Decimal(count) if chosen.unit_price is not None else None
            )
            lines.append(
                PurchaseProposalLine(
                    coverage=item,
                    gap=gap,
                    pack=chosen,
                    packs=count,
                    order_quantity=order_quantity,
                    estimated_cost=cost,
                    note="" if count == 1 else f"单包不足以覆盖缺口，需 {count} 包",
                )
            )
        return PurchaseProposal(tuple(lines))

    # ---------------------------------------------------------------- 内部
    @staticmethod
    def _choose_pack(packs: Iterable[PackSpec], gap: Quantity) -> Optional[PackSpec]:
        """选包装：优先「最小但能覆盖缺口」的规格。

        没有够大的规格时退回最大规格，靠买多包凑——这比「买不到」更接近
        实验室的实际做法。
        """
        candidates = [
            pack for pack in packs if pack.pack_size.unit.dimension is gap.unit.dimension
        ]
        if not candidates:
            return None
        big_enough = [pack for pack in candidates if pack.pack_size >= gap]
        if big_enough:
            return min(big_enough, key=lambda pack: pack.pack_size.base_value())
        return max(candidates, key=lambda pack: pack.pack_size.base_value())

    @staticmethod
    def _packs_needed(pack_size: Quantity, gap: Quantity) -> int:
        if pack_size.base_value() <= 0:
            return 0
        ratio = gap.base_value() / pack_size.base_value()
        return max(1, int(math.ceil(float(ratio))))


def proposal_from_mapping(
    coverage: CoverageReport, packs: Mapping[str, Sequence[PackSpec]]
) -> PurchaseProposal:
    """便捷入口：直接给包装字典，不必先建目录。"""
    return ProcurementPlanner(StaticPackCatalog(packs)).plan(coverage)


__all__ = [
    "PackSpec",
    "PackCatalog",
    "StaticPackCatalog",
    "PurchaseProposalLine",
    "PurchaseProposal",
    "ProcurementPlanner",
    "proposal_from_mapping",
]
