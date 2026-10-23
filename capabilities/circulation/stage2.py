"""第二段：平账台。

受理人报上来的缺口，由**他自己**拿去跟别的管理员调。注意申报人换了：
第一段申报人是教师，第二段申报人是那个缺料的管理员。这也是 BCLRM
现有 ``demand_service.create_demand`` 要求「需求人必须是管理员」的原因
——那条校验不是把教师挡在门外的缺陷，它标出的正是第二段的入口。

库存是**横向同层**关系：管理员之间不是上下级，所以撮合只能靠优先级，
不能靠指派。沿用 BCLRM 既有的顺序：

    同科室优先 → 全院兜底

但有两个硬约束：

1. **必须排除受理人自己。** 他的量在第一段已经算过并承诺出去了，若再
   算一次，同一批料会被承诺两次。
2. **调的是保管权，不是实物出库。** 调完之后瓶子仍在原处（或搬到受理人
   的库位），账面上的 ``manager`` 变了。因此这里产出的是
   :class:`~domain.pipeline.TransferLine`——它带 ``from`` 和 ``to``，
   而第一段的 ``IssueLine`` 刻意没有这两个字段。
"""
from __future__ import annotations

from typing import Optional, Sequence

from capabilities.circulation.ledger import CustodyLedger
from capabilities.supply.evaluator import SupplyEvaluator
from capabilities.supply.stock import StockLot
from domain.custody import Custodian
from domain.pipeline import (
    Acceptance,
    LotPick,
    Shortfall,
    TransferLine,
    TransferProposal,
)
from domain.requirement import RequirementSheet
from domain.units import Quantity

# 撮合优先级：数值越小越先被调
PRIORITY_SAME_DEPARTMENT = 0
PRIORITY_OTHER_DEPARTMENT = 1


class TransferBroker:
    """平账台：缺口 → 从其他管理员处调拨的建议。"""

    def __init__(
        self,
        ledger: CustodyLedger,
        evaluator: Optional[SupplyEvaluator] = None,
        prefer_same_department: bool = True,
    ) -> None:
        self.ledger = ledger
        self.evaluator = evaluator or SupplyEvaluator()
        self.prefer_same_department = prefer_same_department

    # ---------------------------------------------------------------- 主流程
    def broker(self, acceptance: Acceptance) -> TransferProposal:
        """把受理结论里的缺口平掉。

        没有缺口时返回空建议（``is_resolved`` 为真），调用方不必判空。
        """
        sheet = acceptance.shortfall_sheet()
        if sheet is None:
            return TransferProposal(beneficiary=acceptance.custodian)

        beneficiary = acceptance.custodian
        # 剩余待落实量：按物质键跟踪，跨管调拨时逐轮扣减
        remaining: dict[str, Quantity] = {
            line.key: line.quantity for line in sheet.lines
        }
        lines: list[TransferLine] = []

        for supplier in self._candidates(beneficiary):
            if not self._has_remaining(remaining):
                break
            round_sheet = self._sheet_of_remaining(sheet, remaining)
            subset = self.ledger.subset(supplier)
            assessment = self.evaluator.assess(round_sheet, subset)

            for coverage in assessment.coverage.lines:
                key = coverage.requirement.key
                need = remaining.get(key)
                if need is None or need.is_zero():
                    continue
                available = coverage.available
                if available.unit.dimension is not need.unit.dimension:
                    continue
                take = (available if available < need else need).clamp_non_negative()
                if not take.is_positive():
                    continue

                lot_id = self._lot_hint(supplier, coverage.requirement.substance, take)
                lines.append(
                    TransferLine(
                        from_custodian=supplier,
                        to_custodian=beneficiary,
                        substance=coverage.requirement.substance,
                        quantity=take,
                        lot_id=lot_id,
                        priority=self._priority(supplier, beneficiary),
                        note=(
                            "同科室调剂"
                            if supplier.in_department_of(beneficiary)
                            else "跨科室调剂"
                        ),
                    )
                )
                remaining[key] = (need - take).clamp_non_negative()

        unresolved = tuple(
            Shortfall(
                requirement=self._requirement_of(sheet, key),
                quantity=quantity,
                reason="全院可调量不足，需采购",
            )
            for key, quantity in remaining.items()
            if quantity.is_positive()
        )

        return TransferProposal(
            beneficiary=beneficiary,
            lines=tuple(lines),
            unresolved=unresolved,
        )

    # ---------------------------------------------------------------- 候选
    def _candidates(self, beneficiary: Custodian) -> tuple[Custodian, ...]:
        """可调的保管人，排除受理人自己，同科室优先。"""
        others = [
            c for c in self.ledger.custodians() if not c.same_as(beneficiary)
        ]
        if not self.prefer_same_department:
            return tuple(sorted(others, key=lambda c: c.name))
        return tuple(
            sorted(
                others,
                key=lambda c: (
                    self._priority(c, beneficiary),
                    c.name,
                ),
            )
        )

    @staticmethod
    def _priority(supplier: Custodian, beneficiary: Custodian) -> int:
        if supplier.in_department_of(beneficiary):
            return PRIORITY_SAME_DEPARTMENT
        return PRIORITY_OTHER_DEPARTMENT

    # ---------------------------------------------------------------- 细节
    @staticmethod
    def _has_remaining(remaining: dict[str, Quantity]) -> bool:
        return any(q.is_positive() for q in remaining.values())

    @staticmethod
    def _requirement_of(sheet: RequirementSheet, key: str):
        for line in sheet.lines:
            if line.key == key:
                return line
        raise KeyError(f"缺口单里没有物质 {key}")

    @staticmethod
    def _sheet_of_remaining(
        sheet: RequirementSheet, remaining: dict[str, Quantity]
    ) -> RequirementSheet:
        """把"还剩多少没落实"重新包成一张单，喂给评估器。"""
        lines = tuple(
            line.with_quantity(remaining[line.key])
            for line in sheet.lines
            if remaining.get(line.key) is not None and remaining[line.key].is_positive()
        )
        return RequirementSheet(
            recipe_key=sheet.recipe_key,
            title=sheet.title,
            scale=sheet.scale,
            lines=lines,
            source=sheet.source,
        )

    def _lot_hint(self, supplier: Custodian, ref, quantity: Quantity) -> str:
        """给出建议取的瓶（先到期先用）；跨量纲时留空。"""
        lots: Sequence[StockLot] = [
            lot
            for lot in self.ledger.lots(supplier, ref)
            if lot.quantity.unit.dimension is quantity.unit.dimension
        ]
        if not lots:
            return ""
        ordered = sorted(lots, key=lambda lot: lot.fefo_key)
        need = quantity
        picked: list[LotPick] = []
        for lot in ordered:
            if not need.is_positive():
                break
            take = lot.quantity if lot.quantity < need else need
            if take.is_positive():
                picked.append(LotPick(lot.lot_id, take))
                need = need - take
        if not picked:
            return ""
        if need.is_positive():
            # 单瓶不够，给出多瓶（实际执行时按序取，不会超发）
            return ",".join(pick.lot_id for pick in picked)
        return picked[0].lot_id


def broker_gaps(
    acceptance: Acceptance,
    ledger: CustodyLedger,
    evaluator: Optional[SupplyEvaluator] = None,
) -> TransferProposal:
    """函数式入口（脚本、报表用）。"""
    return TransferBroker(ledger, evaluator).broker(acceptance)


__all__ = ["TransferBroker", "broker_gaps", "PRIORITY_SAME_DEPARTMENT", "PRIORITY_OTHER_DEPARTMENT"]
