"""供应评估器：把「一张需求单 + 一份库存快照」算成可执行判断。

为什么单独一个类，而不是让需求单自己去问库存？

- 需求单是领域对象，它只该认识数字，不该认识「瓶」「过期」「管控」。
- 可用量的口径（哪些批次算数）是策略，会变；需求单不该跟着变。
- 库存按体积、需求按质量（或反过来）时，需要**物性换算**，而物性
  来自物质目录——这属于供应侧的适配职责。

于是：``Availability`` 负责「有多少能用」，``SupplyEvaluator`` 负责
「够不够、怎么换算」，业务层只读结论。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domain.requirement import CoverageReport, RequirementSheet
from domain.substance import Substance
from domain.units import Quantity, UnitError
from capabilities.supply.availability import Availability, AvailabilityPolicy, standard_policy
from capabilities.supply.stock import StockSnapshot


@dataclass(frozen=True)
class SupplyAssessment:
    """一次供应评估的完整结论。"""

    availability: Availability
    coverage: CoverageReport
    converted: tuple[str, ...] = ()   # 发生过跨量纲换算的物质名（留痕）

    @property
    def is_fulfillable(self) -> bool:
        return self.coverage.is_fully_covered

    @property
    def shortages(self):
        return self.coverage.shortages

    def summary(self) -> str:
        text = f"{self.coverage.summary()}（{self.availability.policy_label}）"
        if self.converted:
            text += f"；{len(self.converted)} 项按物性做了单位换算：{'、'.join(self.converted)}"
        return text


class SupplyEvaluator:
    """需求单 × 库存快照 → 覆盖结论。"""

    def __init__(self, policy: Optional[AvailabilityPolicy] = None, resolver=None) -> None:
        self._policy = policy or standard_policy()
        self._resolver = resolver

    @property
    def policy(self) -> AvailabilityPolicy:
        return self._policy

    def assess(self, sheet: RequirementSheet, snapshot: StockSnapshot) -> SupplyAssessment:
        """评估一张需求单能否由现有库存满足。"""
        availability = self._policy.evaluate(snapshot)

        mapping: dict[str, Quantity] = {}
        converted: list[str] = []

        for line in sheet.lines:
            unit = line.quantity.unit
            quantity = availability.of(line.substance, unit)
            if quantity.is_zero():
                # 量纲不一致（库存按 mL、需求按 g）：尝试用物性换算
                raw = availability.any_of(line.key)
                if raw is not None and self._resolver is not None:
                    substance = self._resolver.resolve(line.substance) or Substance(line.substance)
                    try:
                        quantity = substance.convert(raw, unit)
                        if not quantity.is_zero():
                            converted.append(line.name)
                    except UnitError:
                        quantity = Quantity.zero(unit)
                else:
                    quantity = Quantity.zero(unit)
            mapping[line.key] = quantity

        coverage = sheet.coverage_with(mapping)
        return SupplyAssessment(
            availability=availability,
            coverage=coverage,
            converted=tuple(dict.fromkeys(converted)),
        )

    def withdraw(self, sheet: RequirementSheet, snapshot: StockSnapshot) -> tuple[CoverageReport, dict]:
        """便捷方法：只要覆盖结论与可用量映射。"""
        assessment = self.assess(sheet, snapshot)
        return assessment.coverage, assessment.availability.mapping_for(sheet)


def assess(sheet: RequirementSheet, snapshot: StockSnapshot, resolver=None,
           policy: Optional[AvailabilityPolicy] = None) -> SupplyAssessment:
    """函数式入口（脚本、测试、报表用）。"""
    return SupplyEvaluator(policy, resolver).assess(sheet, snapshot)


__all__ = ["SupplyAssessment", "SupplyEvaluator", "assess"]
