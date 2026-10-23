"""供应与流转中台测试：库存快照、可用量策略、缺口、采购建议、单据状态机。"""
import os
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capabilities.circulation import (
    CirculationError,
    InMemoryCirculationGateway,
    TicketStatus,
)
from capabilities.metering import CatalogSubstanceResolver, MeteringEngine
from capabilities.supply import (
    AvailabilityPolicy,
    BorrowableOnly,
    ExpiryState,
    HasQuantity,
    NotExpired,
    PackSpec,
    ProcurementPlanner,
    StaticPackCatalog,
    StockLot,
    StockSnapshot,
    SupplyEvaluator,
    WithinDays,
    standard_policy,
    strict_policy,
)
from domain.amount import per_person
from domain.batch import BatchScale
from domain.recipe import Recipe, RecipeComponent
from domain.substance import ComponentRole, Substance, SubstanceRef
from domain.units import Quantity


def _ref(name, cas=None):
    return SubstanceRef.of(name, cas)


def _bottle_row(**overrides):
    row = {
        "bottle_number": "B001",
        "reagent_name": "乙酸酐",
        "cas_number": "108-24-7",
        "remaining_quantity": 500,
        "unit": "mL",
        "borrowable_flag": "可借",
        "borrowable_check": 1,
        "expired_flag": "正常",
        "scrap_flag": None,
        "is_controlled": 0,
        "storage_location": "A-01",
    }
    row.update(overrides)
    return row


class TestStockLotAdapter(unittest.TestCase):
    """库存行 → 批次：中文状态词的唯一翻译点。"""

    def test_normal_row(self):
        lot = StockLot.from_bottle_row(_bottle_row())
        self.assertEqual(lot.lot_id, "B001")
        self.assertEqual(lot.substance.key, "cas:108-24-7")
        self.assertEqual(lot.quantity.value, Decimal("500"))
        self.assertTrue(lot.borrowable)
        self.assertFalse(lot.scrapped)

    def test_borrowed_row_is_not_borrowable(self):
        lot = StockLot.from_bottle_row(_bottle_row(borrowable_flag="已借出"))
        self.assertFalse(lot.borrowable)

    def test_depleted_row(self):
        lot = StockLot.from_bottle_row(_bottle_row(borrowable_flag="耗尽", remaining_quantity=0))
        self.assertTrue(lot.is_empty)

    def test_expired_row(self):
        lot = StockLot.from_bottle_row(_bottle_row(expired_flag="已过期"))
        self.assertEqual(lot.expiry, ExpiryState.EXPIRED)
        self.assertFalse(lot.expiry.is_usable)

    def test_scrapped_row(self):
        lot = StockLot.from_bottle_row(_bottle_row(scrap_flag="待报废"))
        self.assertTrue(lot.scrapped)

    def test_unknown_expiry_word_maps_to_pending(self):
        lot = StockLot.from_bottle_row(_bottle_row(expired_flag="不知道"))
        self.assertEqual(lot.expiry, ExpiryState.UNKNOWN)
        self.assertTrue(lot.expiry.is_usable)

    def test_days_to_expiry(self):
        soon = (date.today() + timedelta(days=10)).isoformat()
        lot = StockLot.from_bottle_row(_bottle_row(expiry_date=soon))
        self.assertEqual(lot.days_to_expiry, 10)


class TestAvailabilityPolicy(unittest.TestCase):
    """策略组合：谁能进可用池。"""

    def setUp(self):
        self.snapshot = StockSnapshot.of(
            [
                StockLot("A", _ref("乙醇", "64-17-5"), Quantity.of("500", "mL")),
                StockLot("B", _ref("乙醇", "64-17-5"), Quantity.of("300", "mL"), expiry=ExpiryState.EXPIRED),
                StockLot("C", _ref("乙醇", "64-17-5"), Quantity.of("200", "mL"), borrowable=False),
                StockLot("D", _ref("乙醇", "64-17-5"), Quantity.of("0", "mL")),
                StockLot("E", _ref("水杨酸", "69-72-7"), Quantity.of("50", "g"), scrapped=True),
            ]
        )

    def test_standard_policy_keeps_only_usable(self):
        availability = standard_policy().evaluate(self.snapshot)
        self.assertEqual(availability.of(_ref("乙醇", "64-17-5"), "mL").value, Decimal("500"))
        # 过期 / 已借出 / 无余量 / 已报废 各一个
        self.assertEqual(len(availability.excluded), 4)

    def test_scrapped_excluded(self):
        availability = standard_policy().evaluate(self.snapshot)
        self.assertEqual(availability.of(_ref("水杨酸", "69-72-7"), "g").value, Decimal("0"))

    def test_exclusion_reasons_are_recorded(self):
        availability = standard_policy().evaluate(self.snapshot)
        reasons = availability.excluded_reasons()
        self.assertIn("已过期", reasons)
        self.assertIn("已借出或已报废", reasons)
        self.assertIn("无剩余量", reasons)

    def test_strict_policy_excludes_near_expiry(self):
        soon = (date.today() + timedelta(days=10)).isoformat()
        snapshot = StockSnapshot.of(
            [
                StockLot(
                    "F", _ref("乙醇", "64-17-5"), Quantity.of("500", "mL"),
                    expiry=ExpiryState.EXPIRING, expires_on=date.fromisoformat(soon),
                )
            ]
        )
        self.assertEqual(standard_policy().evaluate(snapshot).of(_ref("乙醇", "64-17-5"), "mL").value, Decimal("500"))
        self.assertEqual(strict_policy(30).evaluate(snapshot).of(_ref("乙醇", "64-17-5"), "mL").value, Decimal("0"))

    def test_policy_is_composable(self):
        policy = AvailabilityPolicy(HasQuantity(), BorrowableOnly(), NotExpired(), WithinDays(0))
        availability = policy.evaluate(self.snapshot)
        self.assertEqual(availability.of(_ref("乙醇", "64-17-5"), "mL").value, Decimal("500"))

    def test_multi_lot_quantity_sums(self):
        snapshot = StockSnapshot.of(
            [
                StockLot("G", _ref("乙醇", "64-17-5"), Quantity.of("400", "mL")),
                StockLot("H", _ref("乙醇", "64-17-5"), Quantity.of("0.6", "L")),
            ]
        )
        availability = standard_policy().evaluate(snapshot)
        self.assertEqual(availability.of(_ref("乙醇", "64-17-5"), "mL").value, Decimal("1000.0"))


class TestSupplyEvaluator(unittest.TestCase):
    """需求单 × 库存 → 覆盖结论（含跨量纲换算）。"""

    def setUp(self):
        resolver = CatalogSubstanceResolver()
        resolver.add(Substance.of("乙酸酐", cas="108-24-7", formula="C4H6O3", density=1.08))
        resolver.add(Substance.of("水杨酸", cas="69-72-7", formula="C7H6O3"))
        self.resolver = resolver

        recipe = Recipe(
            key="t",
            title="测试配方",
            components=(
                RecipeComponent(_ref("水杨酸", "69-72-7"), ComponentRole.REACTANT, per_person("2", "g"), 0),
                RecipeComponent(_ref("乙酸酐", "108-24-7"), ComponentRole.REACTANT, per_person("1", "g"), 1),
            ),
        )
        self.sheet = MeteringEngine(resolver).plan(recipe, BatchScale.for_persons(10)).sheet

    def test_volume_stock_covers_mass_demand(self):
        """库存 500 mL 乙酸酐（密度 1.08 → 540 g）覆盖 10 g 需求。"""
        snapshot = StockSnapshot.of(
            [
                StockLot("B1", _ref("水杨酸", "69-72-7"), Quantity.of("5", "g")),
                StockLot("B2", _ref("乙酸酐", "108-24-7"), Quantity.of("500", "mL")),
            ]
        )
        assessment = SupplyEvaluator(resolver=self.resolver).assess(self.sheet, snapshot)
        line = [l for l in assessment.coverage.lines if l.requirement.name == "乙酸酐"][0]
        self.assertTrue(line.is_covered)
        self.assertIn("乙酸酐", assessment.converted)

    def test_shortage_when_stock_insufficient(self):
        snapshot = StockSnapshot.of(
            [StockLot("B1", _ref("水杨酸", "69-72-7"), Quantity.of("5", "g"))]
        )
        assessment = SupplyEvaluator(resolver=self.resolver).assess(self.sheet, snapshot)
        self.assertFalse(assessment.is_fulfillable)
        self.assertEqual(len(assessment.shortages), 2)

    def test_unknown_substance_property_does_not_crash(self):
        resolver = CatalogSubstanceResolver()  # 空目录
        snapshot = StockSnapshot.of(
            [StockLot("B2", _ref("乙酸酐", "108-24-7"), Quantity.of("500", "mL"))]
        )
        assessment = SupplyEvaluator(resolver=resolver).assess(self.sheet, snapshot)
        # 缺密度 → 无法换算 → 记零可用，但整张评估不炸
        self.assertFalse(assessment.is_fulfillable)


class TestProcurementPlanner(unittest.TestCase):
    """缺口 → 包装 → 采购建议。"""

    def _coverage(self):
        recipe = Recipe(
            key="p",
            title="采购测试",
            components=(
                RecipeComponent(_ref("乙醇", "64-17-5"), ComponentRole.REAGENT, per_person("10", "mL"), 0),
            ),
        )
        resolver = CatalogSubstanceResolver()
        resolver.add(Substance.of("乙醇", cas="64-17-5", formula="C2H6O", default_unit="mL"))
        sheet = MeteringEngine(resolver).plan(recipe, BatchScale.for_persons(12)).sheet
        return sheet.coverage_with({"cas:64-17-5": Quantity.of("20", "mL")})

    def test_chooses_smallest_covering_pack(self):
        """缺口 100 mL（120 需求 - 20 库存）→ 选 100 mL 那档，不是 500 mL。"""
        key = "cas:64-17-5"
        catalog = StaticPackCatalog(
            {
                key: [
                    PackSpec(key, Quantity.of("100", "mL"), "甲", Decimal("10")),
                    PackSpec(key, Quantity.of("500", "mL"), "乙", Decimal("38.5")),
                    PackSpec(key, Quantity.of("1", "L"), "丙", Decimal("70")),
                ]
            }
        )
        proposal = ProcurementPlanner(catalog).plan(self._coverage())
        self.assertEqual(len(proposal), 1)
        line = proposal.lines[0]
        self.assertEqual(line.pack.pack_size.value, Decimal("100"))
        self.assertEqual(line.packs, 1)
        self.assertEqual(line.estimated_cost, Decimal("10"))

    def test_multiple_packs_when_gap_exceeds_largest(self):
        """缺口 100 mL，最大包装只有 50 mL → 买 2 包凑。"""
        key = "cas:64-17-5"
        catalog = StaticPackCatalog(
            {key: [PackSpec(key, Quantity.of("50", "mL"), "甲", Decimal("6"))]}
        )
        proposal = ProcurementPlanner(catalog).plan(self._coverage())
        line = proposal.lines[0]
        self.assertEqual(line.packs, 2)
        self.assertEqual(line.order_quantity.value, Decimal("100"))
        self.assertEqual(line.estimated_cost, Decimal("12"))

    def test_no_pack_spec_yields_unpriced_line(self):
        proposal = ProcurementPlanner(StaticPackCatalog()).plan(self._coverage())
        line = proposal.lines[0]
        self.assertIsNone(line.pack)
        self.assertIn("询价", line.note)
        self.assertEqual(proposal.estimated_cost, Decimal("0"))

    def test_no_shortage_no_proposal(self):
        coverage = self._coverage()
        full = coverage.lines[0].requirement.quantity
        satisfied = coverage.__class__(
            (coverage.lines[0].__class__(coverage.lines[0].requirement, full),)
        )
        self.assertEqual(len(ProcurementPlanner(StaticPackCatalog()).plan(satisfied)), 0)


class TestCirculationGateway(unittest.TestCase):
    """流转网关：状态机与关键控制点。"""

    def setUp(self):
        self.gateway = InMemoryCirculationGateway()
        self.sheet = StockSnapshot  # 占位，避免误用
        recipe = Recipe(
            key="g",
            title="单据测试",
            components=(
                RecipeComponent(_ref("乙醇", "64-17-5"), ComponentRole.REAGENT, per_person("1", "mL"), 0),
            ),
        )
        resolver = CatalogSubstanceResolver()
        resolver.add(Substance.of("乙醇", cas="64-17-5", formula="C2H6O", default_unit="mL"))
        self.requirement = MeteringEngine(resolver).plan(recipe, BatchScale.for_persons(2)).sheet

    def test_full_lifecycle(self):
        ticket = self.gateway.submit(self.requirement, "张老师")
        self.assertEqual(ticket.status, TicketStatus.SUBMITTED)
        self.assertEqual(len(ticket.events), 1)

        approved = self.gateway.approve(ticket.ticket_no, "李管理员")
        self.assertEqual(approved.status, TicketStatus.APPROVED)

        issued = self.gateway.issue(ticket.ticket_no, "王库管")
        self.assertEqual(issued.status, TicketStatus.ISSUED)
        self.assertTrue(issued.is_open)

        closed = self.gateway.close(ticket.ticket_no, "王库管")
        self.assertEqual(closed.status, TicketStatus.CLOSED)
        self.assertFalse(closed.is_open)
        self.assertEqual(len(closed.events), 4)

    def test_self_approval_blocked(self):
        ticket = self.gateway.submit(self.requirement, "张老师")
        with self.assertRaises(CirculationError) as ctx:
            self.gateway.approve(ticket.ticket_no, "张老师")
        self.assertIn("不能审批自己", str(ctx.exception))

    def test_illegal_transition_blocked(self):
        ticket = self.gateway.submit(self.requirement, "张老师")
        with self.assertRaises(CirculationError):
            self.gateway.issue(ticket.ticket_no, "王库管")  # 未审批不能发放

    def test_empty_requester_rejected(self):
        with self.assertRaises(CirculationError):
            self.gateway.submit(self.requirement, "   ")

    def test_unknown_ticket(self):
        with self.assertRaises(CirculationError):
            self.gateway.get("不存在")


if __name__ == "__main__":
    unittest.main()
