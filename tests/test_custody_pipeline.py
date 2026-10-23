"""两段管线的行为测试。

这里测的不是算术，而是**职责边界**。两段管线唯一容易搞错的地方就是
边界——谁受理、谁补料、谁能动别人的瓶子。算术错了看得见，边界错了
要等到期末盘库才发现。

每个测试的注释都写清「这条约束如果不成立，现实里会发生什么」。
"""
import unittest
from decimal import Decimal

from capabilities.circulation import (
    CompositeRouter,
    AcceptanceDesk,
    EmptyLedger,
    MaterialPipeline,
    RoutingError,
    SnapshotLedger,
    SourceRouter,
    StaticRouter,
    TransferBroker,
)
from capabilities.supply import ExpiryState, StockLot, StockSnapshot, SupplyEvaluator
from capabilities.metering import CatalogSubstanceResolver
from domain import (
    Acceptance,
    BatchScale,
    ComponentRole,
    Custodian,
    Quantity,
    RequirementLine,
    RequirementSheet,
    SourceRef,
    Substance,
    SubstanceRef,
    TeacherRequest,
    parse_unit,
)


# ---------------------------------------------------------------------------
# 构造工具
# ---------------------------------------------------------------------------
SALICYLIC = SubstanceRef.of("水杨酸", "69-72-7", "C7H6O3")
ANHYDRIDE = SubstanceRef.of("乙酸酐", "108-24-7", "C4H6O3")
SULFURIC = SubstanceRef.of("硫酸", "7664-93-9", "H2SO4")
ETHANOL = SubstanceRef.of("乙醇", "64-17-5", "C2H6O")

DEPARTMENTS = {
    "李管理员": "化学教研室",
    "王管理员": "化学教研室",
    "赵管理员": "物理化学教研室",
}


def lot(lot_id, ref, value, unit, custodian, expiry=ExpiryState.FRESH):
    return StockLot(
        lot_id=lot_id,
        substance=ref,
        quantity=Quantity.of(value, unit),
        expiry=expiry,
        custodian=custodian,
    )


def ledger_of(lots):
    return SnapshotLedger(
        StockSnapshot.of(lots), department_of=lambda name: DEPARTMENTS.get(name, "")
    )


def resolver():
    catalog = CatalogSubstanceResolver()
    for substance in [
        Substance.of("水杨酸", cas="69-72-7", formula="C7H6O3"),
        Substance.of("乙酸酐", cas="108-24-7", formula="C4H6O3", density=1.08),
        Substance.of("硫酸", cas="7664-93-9", formula="H2SO4", density=1.84),
        Substance.of("乙醇", cas="64-17-5", formula="C2H6O", density=0.789),
    ]:
        catalog.add(substance)
    return catalog


def sheet_of(lines):
    return RequirementSheet(
        recipe_key="teach:aspirin",
        title="乙酰水杨酸制备",
        scale=BatchScale.for_persons(12),
        lines=tuple(
            RequirementLine(ref, role, Quantity.of(value, unit), basis, seq=index)
            for index, (ref, role, value, unit, basis) in enumerate(lines)
        ),
    )


def teaching_request(sheet, requester="张老师", course="有机化学实验", klass="应化2301"):
    return TeacherRequest(
        requester=requester,
        sheet=sheet,
        source=SourceRef.teaching(course, klass),
        due_hint="周三下午",
    )


# ===========================================================================
# 一、保管权的语义
# ===========================================================================
class CustodianSemanticsTest(unittest.TestCase):
    """保管权是「临时所有」，不是「使用」。"""

    def test_teacher_never_becomes_custodian(self):
        """教师申领之后，保管账里不该多出教师这一栏。

        如果这条不成立，后果是：教师名下凭空出现「持有一瓶硫酸」，
        期末盘库时他会收到一张自己都不知道的欠条。
        """
        ledger = ledger_of([lot("B1", SALICYLIC, 100, "g", "李管理员")])
        request = teaching_request(
            sheet_of([(SALICYLIC, ComponentRole.REACTANT, 24, "g", "人均 2 g")])
        )
        acceptance = AcceptanceDesk(
            SourceRouter({"有机化学实验": Custodian.of("李管理员", "化学教研室")}), ledger
        ).receive(request)

        names = {c.name for c in ledger.custodians()}
        self.assertNotIn("张老师", names)
        self.assertEqual(acceptance.custodian.name, "李管理员")

    def test_issue_line_has_no_recipient_field(self):
        """第一段的发放行不带「转给谁」——那段不动保管权。

        一旦 IssueLine 也能填 to_custodian，就会有人在业务层图省事，
        把教师写成新保管人，两段立刻混成一段。
        """
        ledger = ledger_of([lot("B1", SALICYLIC, 100, "g", "李管理员")])
        request = teaching_request(
            sheet_of([(SALICYLIC, ComponentRole.REACTANT, 24, "g", "人均 2 g")])
        )
        acceptance = AcceptanceDesk(
            SourceRouter({"有机化学实验": Custodian.of("李管理员", "化学教研室")}), ledger
        ).receive(request)

        issued = acceptance.issued[0]
        self.assertFalse(hasattr(issued, "to_custodian"))
        self.assertFalse(hasattr(issued, "from_custodian"))

    def test_transfer_line_carries_both_sides(self):
        """第二段的调拨行必须写明「从谁到谁」——那段动的正是保管权。"""
        ledger = ledger_of(
            [
                lot("B-LI", SALICYLIC, 10, "g", "李管理员"),
                lot("B-WANG", SALICYLIC, 50, "g", "王管理员"),
            ]
        )
        request = teaching_request(
            sheet_of([(SALICYLIC, ComponentRole.REACTANT, 24, "g", "人均 2 g")])
        )
        pipeline = MaterialPipeline(
            SourceRouter({"有机化学实验": Custodian.of("李管理员", "化学教研室")}), ledger
        )
        result = pipeline.run(request)

        line = result.proposal.lines[0]
        self.assertEqual(line.from_custodian.name, "王管理员")
        self.assertEqual(line.to_custodian.name, "李管理员")


# ===========================================================================
# 二、第一段：只报自己名下
# ===========================================================================
class IntakeStageTest(unittest.TestCase):
    """受理台不得越界全院撮合。"""

    def setUp(self):
        self.router = SourceRouter({"有机化学实验": Custodian.of("李管理员", "化学教研室")})

    def test_does_not_borrow_from_others(self):
        """李名下的水杨酸只有 10 g，需求 24 g：只能发 10 g，剩下的记缺口。

        若受理台自己去隔壁借足 24 g，李管理员永远不会知道自己缺 14 g，
        也就永远不会去补货——库房就这样慢慢被掏空而无人负责。
        """
        ledger = ledger_of(
            [
                lot("B-LI", SALICYLIC, 10, "g", "李管理员"),
                lot("B-WANG", SALICYLIC, 500, "g", "王管理员"),
            ]
        )
        acceptance = AcceptanceDesk(self.router, ledger).receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 24, "g", "")]))
        )

        self.assertEqual(len(acceptance.issued), 1)
        self.assertEqual(acceptance.issued[0].quantity.value, Decimal("10"))
        self.assertEqual(acceptance.issued[0].lot_id, "B-LI")
        self.assertEqual(len(acceptance.shortfalls), 1)
        self.assertEqual(acceptance.shortfalls[0].quantity.value, Decimal("14"))
        self.assertFalse(acceptance.is_complete)

    def test_complete_when_own_stock_suffices(self):
        """名下的量够时不该产生任何缺口，也不该去碰别人的账。"""
        ledger = ledger_of(
            [
                lot("B-LI", SALICYLIC, 100, "g", "李管理员"),
                lot("B-WANG", SALICYLIC, 500, "g", "王管理员"),
            ]
        )
        acceptance = AcceptanceDesk(self.router, ledger).receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 24, "g", "")]))
        )

        self.assertTrue(acceptance.is_complete)
        self.assertEqual(acceptance.issued[0].lot_id, "B-LI")
        self.assertEqual(acceptance.shortfalls, ())

    def test_picks_earliest_expiry_first(self):
        """先到期先用。不这么做，临期的瓶会一直压在架上直到报废。"""
        ledger = ledger_of(
            [
                lot("B-LATE", SALICYLIC, 100, "g", "李管理员", ExpiryState.FRESH),
                lot("B-SOON", SALICYLIC, 30, "g", "李管理员", ExpiryState.EXPIRING),
            ]
        )
        acceptance = AcceptanceDesk(self.router, ledger).receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 20, "g", "")]))
        )
        self.assertEqual(acceptance.issued[0].lot_id, "B-SOON")

    def test_multiple_bottles_are_listed(self):
        """单瓶不够时列全瓶号，不假装只发一瓶。"""
        ledger = ledger_of(
            [
                lot("B1", SALICYLIC, 10, "g", "李管理员"),
                lot("B2", SALICYLIC, 10, "g", "李管理员"),
                lot("B3", SALICYLIC, 10, "g", "李管理员"),
            ]
        )
        acceptance = AcceptanceDesk(self.router, ledger).receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 25, "g", "")]))
        )
        self.assertEqual(acceptance.issued[0].lot_id, "B1,B2,B3")
        self.assertEqual(acceptance.issued[0].quantity.value, Decimal("25"))

    def test_unclaimed_bottles_are_reported_not_used(self):
        """没人认领的瓶不能借，但必须说出来。

        不说的话，老师看到「账上明明有 999 g」却领不到，会以为系统坏了。
        """
        ledger = ledger_of(
            [
                lot("B-LI", SALICYLIC, 5, "g", "李管理员"),
                lot("B-NOBODY", SALICYLIC, 999, "g", ""),
            ]
        )
        acceptance = AcceptanceDesk(self.router, ledger).receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 24, "g", "")]))
        )

        self.assertEqual(acceptance.issued[0].quantity.value, Decimal("5"))
        self.assertEqual(acceptance.shortfalls[0].quantity.value, Decimal("19"))
        self.assertTrue(
            any("未指定保管人" in note for note in acceptance.notes),
            f"应当提示未认领批次，实际 notes={acceptance.notes}",
        )

    def test_missing_route_raises_instead_of_guessing(self):
        """没配受理人时必须报错。

        系统"猜一个人"受理，事后没人认这笔账——比直接失败危险得多。
        """
        router = SourceRouter({})
        ledger = ledger_of([lot("B1", SALICYLIC, 100, "g", "李管理员")])
        with self.assertRaises(RoutingError):
            AcceptanceDesk(router, ledger).receive(
                teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 1, "g", "")]))
            )

    def test_course_level_rule_matches_class_level_source(self):
        """配了「有机化学实验」就应该能受理「有机化学实验/应化2301」。"""
        router = SourceRouter({"有机化学实验": Custodian.of("李管理员")})
        ledger = ledger_of([lot("B1", SALICYLIC, 100, "g", "李管理员")])
        acceptance = AcceptanceDesk(router, ledger).receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 1, "g", "")]))
        )
        self.assertEqual(acceptance.custodian.name, "李管理员")

    def test_class_level_rule_wins_over_course_level(self):
        """两个粒度都配了时，精确的班级规则优先。"""
        router = SourceRouter(
            {
                "有机化学实验": Custodian.of("李管理员"),
                "有机化学实验/应化2301": Custodian.of("王管理员"),
            }
        )
        ledger = ledger_of(
            [
                lot("B-LI", SALICYLIC, 100, "g", "李管理员"),
                lot("B-WANG", SALICYLIC, 100, "g", "王管理员"),
            ]
        )
        acceptance = AcceptanceDesk(router, ledger).receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 1, "g", "")]))
        )
        self.assertEqual(acceptance.custodian.name, "王管理员")


# ===========================================================================
# 三、两段之间的传递
# ===========================================================================
class HandoffTest(unittest.TestCase):
    """缺口是唯一被允许穿过两段的东西。"""

    def _acceptance(self):
        ledger = ledger_of(
            [
                lot("B-LI", SALICYLIC, 10, "g", "李管理员"),
                lot("B-WANG", SALICYLIC, 50, "g", "王管理员"),
            ]
        )
        router = SourceRouter({"有机化学实验": Custodian.of("李管理员", "化学教研室")})
        return AcceptanceDesk(router, ledger).receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 24, "g", "")]))
        )

    def test_shortfall_sheet_carries_exact_gap(self):
        """传递出去的单子里只有缺口量，不含已发的部分。"""
        acceptance = self._acceptance()
        gap_sheet = acceptance.shortfall_sheet()

        self.assertIsNotNone(gap_sheet)
        self.assertEqual(len(gap_sheet.lines), 1)
        self.assertEqual(gap_sheet.lines[0].quantity.value, Decimal("14"))
        self.assertTrue(gap_sheet.recipe_key.endswith(":gap"))

    def test_shortfall_sheet_is_none_when_complete(self):
        """名下就够时不该造出第二段的任务。"""
        ledger = ledger_of([lot("B-LI", SALICYLIC, 100, "g", "李管理员")])
        router = SourceRouter({"有机化学实验": Custodian.of("李管理员")})
        acceptance = AcceptanceDesk(router, ledger).receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 24, "g", "")]))
        )
        self.assertIsNone(acceptance.shortfall_sheet())

    def test_invariant_issued_plus_shortfall_equals_demand(self):
        """实发 + 缺口 = 原始需求。料不许凭空消失。"""
        acceptance = self._acceptance()
        original = acceptance.request.sheet.lines[0]
        issued = sum(
            (line.quantity for line in acceptance.issued), Quantity.zero(original.quantity.unit)
        )
        gap = acceptance.shortfall_of(SALICYLIC).quantity
        total = (issued + gap).value
        self.assertEqual(total, original.quantity.value)


# ===========================================================================
# 四、第二段：平账
# ===========================================================================
class RebalanceStageTest(unittest.TestCase):
    """调别人的料，不调自己的。"""

    def _run(self, lots, demand=24):
        ledger = ledger_of(lots)
        router = SourceRouter({"有机化学实验": Custodian.of("李管理员", "化学教研室")})
        pipeline = MaterialPipeline(router, ledger)
        acceptance = pipeline.receive(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, demand, "g", "")]))
        )
        return acceptance, pipeline.settle(acceptance)

    def test_excludes_beneficiary_from_suppliers(self):
        """绝不能从受理人自己的账面再调一次。

        他的量在第一段已经承诺出去了；再算一次会把同一批料承诺两遍，
        账面上就会凭空多出 14 g。
        """
        acceptance, result = self._run(
            [
                lot("B-LI", SALICYLIC, 10, "g", "李管理员"),
                lot("B-WANG", SALICYLIC, 50, "g", "王管理员"),
            ]
        )
        suppliers = {line.from_custodian.name for line in result.proposal.lines}
        self.assertNotIn("李管理员", suppliers)
        self.assertEqual(suppliers, {"王管理员"})

    def test_prefers_same_department(self):
        """同科室优先：跨科室调货要走更多手续，能省则省。"""
        acceptance, result = self._run(
            [
                lot("B-LI", SALICYLIC, 0, "g", "李管理员"),
                lot("B-ZHAO", SALICYLIC, 100, "g", "赵管理员"),   # 外院，量更大
                lot("B-WANG", SALICYLIC, 30, "g", "王管理员"),    # 同科室，量小
            ],
            demand=24,
        )
        lines = result.proposal.lines
        self.assertEqual(lines[0].from_custodian.name, "王管理员")
        self.assertEqual(lines[0].quantity.value, Decimal("24"))

    def test_spans_multiple_suppliers_when_needed(self):
        """一个人不够时继续找下一个。"""
        acceptance, result = self._run(
            [
                lot("B-LI", SALICYLIC, 0, "g", "李管理员"),
                lot("B-WANG", SALICYLIC, 10, "g", "王管理员"),
                lot("B-ZHAO", SALICYLIC, 100, "g", "赵管理员"),
            ],
            demand=24,
        )
        self.assertEqual(len(result.proposal.lines), 2)
        total = sum(line.quantity.value for line in result.proposal.lines)
        self.assertEqual(total, Decimal("24"))
        self.assertTrue(result.proposal.is_resolved)

    def test_unresolved_goes_to_purchase(self):
        """全院都不够的部分转采购，不是悄悄少发。"""
        acceptance, result = self._run(
            [
                lot("B-LI", SALICYLIC, 5, "g", "李管理员"),
                lot("B-WANG", SALICYLIC, 5, "g", "王管理员"),
            ],
            demand=30,
        )
        self.assertFalse(result.is_fulfilled)
        self.assertTrue(result.needs_purchase)
        unresolved = result.proposal.unresolved
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0].quantity.value, Decimal("20"))

        purchase = result.purchase_sheet
        self.assertIsNotNone(purchase)
        self.assertEqual(purchase.lines[0].quantity.value, Decimal("20"))

    def test_fulfilled_when_transfers_cover_gap(self):
        """调拨能平掉时，整条线算"可落实"。"""
        acceptance, result = self._run(
            [
                lot("B-LI", SALICYLIC, 10, "g", "李管理员"),
                lot("B-WANG", SALICYLIC, 50, "g", "王管理员"),
            ]
        )
        self.assertTrue(result.is_fulfilled)
        self.assertFalse(result.needs_purchase)

    def test_empty_ledger_does_not_crash(self):
        """还没接库存时，第一段报缺口、第二段报需采购，不抛异常。"""
        pipeline = MaterialPipeline(
            SourceRouter({"有机化学实验": Custodian.of("李管理员")}), EmptyLedger()
        )
        result = pipeline.run(
            teaching_request(sheet_of([(SALICYLIC, ComponentRole.REACTANT, 10, "g", "")]))
        )
        self.assertTrue(result.acceptance.is_empty)
        self.assertTrue(result.needs_purchase)


# ===========================================================================
# 五、跨量纲与多物质
# ===========================================================================
class CrossDimensionTest(unittest.TestCase):
    """库存按体积、需求按质量时的行为。"""

    def test_convertible_but_lot_id_left_blank(self):
        """乙酸酐库存记 mL、需求记 g：能算出发放量，但不知道是哪一瓶。

        这时如实留空瓶号，让现场按折算量取——比假装"就是这一瓶"
        然后在账上写一个错数字要好。
        """
        ledger = ledger_of([lot("B-LI", ANHYDRIDE, 500, "mL", "李管理员")])
        router = SourceRouter({"有机化学实验": Custodian.of("李管理员")})
        acceptance = AcceptanceDesk(
            router, ledger, SupplyEvaluator(resolver=resolver())
        ).receive(
            teaching_request(sheet_of([(ANHYDRIDE, ComponentRole.REACTANT, 44, "g", "")]))
        )

        self.assertEqual(len(acceptance.issued), 1)
        self.assertEqual(acceptance.issued[0].lot_id, "")
        self.assertTrue(acceptance.is_complete)
        self.assertTrue(
            any("折算" in note for note in acceptance.notes),
            f"应说明按折算量发放，notes={acceptance.notes}",
        )

    def test_mixed_dimensions_do_not_merge(self):
        """同一物质既有 g 又有 mL 时，两条持有量并列，不相加。"""
        ledger = ledger_of(
            [
                lot("B1", ETHANOL, 500, "mL", "李管理员"),
                lot("B2", ETHANOL, 200, "g", "李管理员"),
            ]
        )
        holdings = ledger.holdings()
        rows = [h for h in holdings if h.substance.key == ETHANOL.key]
        self.assertEqual(len(rows), 2)
        units = {h.quantity.unit.symbol for h in rows}
        self.assertEqual(units, {"mL", "g"})


# ===========================================================================
# 六、真实课堂场景（一条完整链路）
# ===========================================================================
class FullScenarioTest(unittest.TestCase):
    """乙酰水杨酸制备：四位老师、三名管理员、一个未认领的瓶。"""

    def setUp(self):
        self.lots = [
            lot("B-LI-01", SALICYLIC, 10, "g", "李管理员"),
            lot("B-LI-02", ANHYDRIDE, 500, "mL", "李管理员"),
            lot("B-LI-03", SULFURIC, 500, "mL", "李管理员"),
            lot("B-WANG-01", SALICYLIC, 50, "g", "王管理员"),
            lot("B-ZHAO-01", ETHANOL, 1, "L", "赵管理员"),
            lot("B-NOBODY", SALICYLIC, 999, "g", ""),
        ]
        self.sheet = sheet_of(
            [
                (SALICYLIC, ComponentRole.REACTANT, 24, "g", "人均 2 g"),
                (ANHYDRIDE, ComponentRole.REACTANT, 44, "g", "2.5 当量"),
                (SULFURIC, ComponentRole.CATALYST, 5, "mL", "0.05 当量"),
                (ETHANOL, ComponentRole.SOLVENT, 72, "mL", "3 倍体积"),
            ]
        )

    def test_two_stage_walkthrough(self):
        ledger = ledger_of(self.lots)
        router = CompositeRouter(
            SourceRouter({"有机化学实验": Custodian.of("李管理员", "化学教研室")})
        )
        pipeline = MaterialPipeline(router, ledger, SupplyEvaluator(resolver=resolver()))
        result = pipeline.run(teaching_request(self.sheet))

        # 第一段：李受理，水杨酸发 10 g 缺 14 g，乙醇完全没有
        acceptance = result.acceptance
        self.assertEqual(acceptance.custodian.name, "李管理员")
        self.assertEqual(len(acceptance.issued), 3)
        self.assertEqual(len(acceptance.shortfalls), 2)
        self.assertEqual(acceptance.shortfall_of(SALICYLIC).quantity.value, Decimal("14"))
        self.assertEqual(acceptance.shortfall_of(ETHANOL).quantity.value, Decimal("72"))

        # 第二段：水杨酸找同科室王，乙醇找外院赵
        proposal = result.proposal
        self.assertEqual(len(proposal.lines), 2)
        by_ref = {line.substance.key: line for line in proposal.lines}
        self.assertEqual(by_ref[SALICYLIC.key].from_custodian.name, "王管理员")
        self.assertEqual(by_ref[ETHANOL.key].from_custodian.name, "赵管理员")
        self.assertTrue(result.is_fulfilled)

        # 全链路可读：老师能看到"该找谁、谁不够、从谁那调"
        trace = "\n".join(result.trace)
        self.assertIn("李管理员", trace)
        self.assertIn("王管理员", trace)
        self.assertIn("赵管理员", trace)

    def test_result_is_serializable(self):
        """结果要能落档：事后查"当时按什么算的"。"""
        pipeline = MaterialPipeline(
            SourceRouter({"有机化学实验": Custodian.of("李管理员", "化学教研室")}),
            ledger_of(self.lots),
            SupplyEvaluator(resolver=resolver()),
        )
        record = pipeline.run(teaching_request(self.sheet)).to_record()

        self.assertEqual(record["request"]["requester"], "张老师")
        self.assertEqual(record["acceptance"]["custodian"], "李管理员")
        self.assertEqual(len(record["acceptance"]["shortfalls"]), 2)
        self.assertEqual(len(record["proposal"]["transfers"]), 2)
        self.assertTrue(record["is_fulfilled"])


if __name__ == "__main__":
    unittest.main()
