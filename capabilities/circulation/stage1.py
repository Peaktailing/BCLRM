"""第一段：受理台。

教师把申请递过来，受理管理员只做一件事——**报自己名下够不够**。

这个「只报自己的」不是保守，是职责边界：

- 如果他名下的量够，料直接发出去（保管权仍在他名下），申请结束
- 如果他名下不够，差额就是第二段的工单，也是他的补料责任

一旦允许受理台越界去全院撮合，"够不够"就变成"全院够不够"，于是：

1. 管理员永远看不到自己的缺口 → 没人补货
2. 第二段的调配单永远不会产生 → 横向流转形同虚设
3. 教师拿到的料不知道是谁批的 → 出了事找不到责任人

所以本类刻意**只接受一个保管人的子快照**，物理上不可能越界。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from capabilities.circulation.ledger import CustodyLedger
from capabilities.circulation.routing import CustodianRouter
from capabilities.supply.evaluator import SupplyEvaluator
from capabilities.supply.stock import StockLot
from domain.custody import Custodian
from domain.pipeline import (
    Acceptance,
    IssueLine,
    LotPick,
    Shortfall,
    TeacherRequest,
)
from domain.requirement import CoverageLine
from domain.units import Quantity


class AcceptanceDesk:
    """受理台：教师申请 → 受理管理员的承诺与缺口。"""

    def __init__(
        self,
        router: CustodianRouter,
        ledger: CustodyLedger,
        evaluator: Optional[SupplyEvaluator] = None,
    ) -> None:
        self.router = router
        self.ledger = ledger
        self.evaluator = evaluator or SupplyEvaluator()

    # ---------------------------------------------------------------- 主流程
    def receive(self, request: TeacherRequest) -> Acceptance:
        """受理一张申请。

        Raises:
            RoutingError: 没有为该申请指派受理人（配置缺失，不是业务失败）。
        """
        custodian = self.router.route(request)

        # 只拿这个人名下的快照——越界在类型层面就不可能
        subset = self.ledger.subset(custodian)
        assessment = self.evaluator.assess(request.sheet, subset)

        issued: list[IssueLine] = []
        shortfalls: list[Shortfall] = []
        notes: list[str] = []

        for coverage in assessment.coverage.lines:
            requirement = coverage.requirement
            granted = self._granted_quantity(coverage)

            if granted.is_positive():
                issued.append(
                    self._make_issue(coverage, granted, custodian, notes)
                )
            if not coverage.is_covered:
                shortfalls.append(
                    Shortfall(
                        requirement=requirement,
                        quantity=coverage.gap,
                        reason=self._shortfall_reason(coverage, custodian.name),
                    )
                )

        if assessment.converted:
            notes.append(
                "按物性做了单位换算：" + "、".join(assessment.converted)
            )
        notes.extend(self._unclaimed_notes(request))

        return Acceptance(
            custodian=custodian,
            request=request,
            issued=tuple(issued),
            shortfalls=tuple(shortfalls),
            notes=tuple(notes),
        )

    # ---------------------------------------------------------------- 细节
    @staticmethod
    def _granted_quantity(coverage: CoverageLine) -> Quantity:
        """本行实际能发多少 = 需求 与 可用 的较小值。"""
        required = coverage.required
        available = coverage.available
        if available.unit.dimension is not required.unit.dimension:
            return Quantity.zero(required.unit)
        smaller = available if available < required else required
        return smaller.clamp_non_negative()

    def _make_issue(
        self,
        coverage: CoverageLine,
        granted: Quantity,
        custodian: Custodian,
        notes: list[str],
    ) -> IssueLine:
        requirement = coverage.requirement
        custodian_note = custodian.describe()
        picks = self._pick_lots(custodian, requirement.substance, granted)
        if not picks:
            # 跨量纲发放（库存记 mL、需求记 g）：算得出总量，但没法预先指定
            # 具体哪一瓶——由现场按折算量取。这里如实说明，不假装知道批号。
            notes.append(
                f"{requirement.name} 按物性折算发放 {granted.format(3)}，"
                "具体取瓶由发放人现场指定"
            )
            return IssueLine(
                substance=requirement.substance,
                quantity=granted,
                lot_id="",
                note=f"{custodian_note} 名下，按折算量发放",
                seq=requirement.seq,
            )
        total = Quantity.zero(granted.unit)
        for pick in picks:
            total = total + pick.quantity
        primary = picks[0].lot_id if len(picks) == 1 else ",".join(p.lot_id for p in picks)
        return IssueLine(
            substance=requirement.substance,
            quantity=total,
            lot_id=primary,
            note=f"{custodian_note} 名下" + (f"，共 {len(picks)} 瓶" if len(picks) > 1 else ""),
            seq=requirement.seq,
        )

    def _pick_lots(
        self, custodian: Custodian, ref, quantity: Quantity
    ) -> tuple[LotPick, ...]:
        """按「先到期先用」从**受理人名下**该物质的批次上取量。

        量纲对不上时返回空——那种情况下不该假装知道是哪一瓶。
        """
        lots = self._sorted_lots(custodian, ref, quantity.unit)
        remaining = quantity
        picks: list[LotPick] = []
        for lot in lots:
            if remaining.base_value() <= 0:
                break
            take = lot.quantity if lot.quantity < remaining else remaining
            if take.is_positive():
                picks.append(LotPick(lot_id=lot.lot_id, quantity=take))
                remaining = remaining - take
        return tuple(picks)

    def _sorted_lots(self, custodian: Custodian, ref, unit) -> Sequence[StockLot]:
        """受理人名下同量纲批次，先到期先用（FEFO）。

        只从 ``ledger.lots(custodian, ...)`` 取，不可能拿到别人的瓶子。
        """
        lots = [
            lot
            for lot in self.ledger.lots(custodian, ref)
            if lot.quantity.unit.dimension is unit.dimension
        ]
        return tuple(sorted(lots, key=lambda lot: lot.fefo_key))

    def _shortfall_reason(self, coverage: CoverageLine, custodian_name: str) -> str:
        if coverage.available.is_zero():
            return f"{custodian_name} 名下无可用"
        return f"{custodian_name} 名下仅 {coverage.available.format(2)}"

    def _unclaimed_notes(self, request: TeacherRequest) -> list[str]:
        """提示「账上有、但没人认领」的量。

        这类批次不参与任何一段，如果不说，看起来就是凭空消失的库存。
        """
        unclaimed = self.ledger.unclaimed()
        if not len(unclaimed):
            return []
        wanted = {line.key for line in request.sheet.lines}
        hits = [lot for lot in unclaimed if lot.substance.key in wanted]
        if not hits:
            return []
        names = sorted({lot.substance.name or lot.substance.key for lot in hits})
        return [
            f"{len(hits)} 个批次（{'、'.join(names)}）未指定保管人，"
            "需先认领才能进入流转"
        ]


__all__ = ["AcceptanceDesk"]
