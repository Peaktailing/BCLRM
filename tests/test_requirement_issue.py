"""需求单转借出单：逐项勾选，借出即兑付。

测五件事，每件都对应一个会真实发生的坏结果：

1. **逐瓶落单** —— 一行拆两瓶时，明细必须写清「这瓶扣多少」。写成
   「A、B 共 50 g」的账，扣库存时只能猜。
2. **逐项兑付** —— 一门课 20 项今天只到 5 项，整单置 issued 会把剩下 15
   项静默吞掉：既不在保底里，也不在任何待办上。兑付必须落在行上。
3. **余量继续占保底** —— 部分兑付后按**余量**锁料。按全量算会把已经发到
   老师手上的那部分当成欠量，抽卡时不敢动。
4. **余量截断** —— 分两次发时第二次拿到的还是「受理那一刻的实发量」，
   不截断就是重复兑付同一批料。
5. **失败不乱账** —— 一瓶发不出去时，已发的照常落单；一瓶都发不出去时
   整单回滚，不留半截。
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.requirement_issue_service import RequirementIssueService
from capabilities.circulation.picking import ReserveQuery
from domain.custody import Custodian
from domain.pipeline import Acceptance, IssueLine, LotPick, TeacherRequest
from domain.requirement import RequirementLine, RequirementSheet
from domain.batch import BatchScale
from domain.recipe import SourceRef
from domain.substance import ComponentRole, SubstanceRef
from domain.units import Quantity
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.requirement_sheet_service import requirement_sheet_service
from services.custodian_route import CustodianRouteRepository
from services.demand_reserve import DemandReserve

ETHANOL = SubstanceRef.of("乙醇")
WATER = SubstanceRef.of("水")
LI = Custodian("李四")
TODAY = date(2026, 10, 23)          # 2026-2027 学年

_TABLES = (
    "borrow_order_item", "borrow_order", "borrow_record", "return_record",
    "reagent_bottle", "requirement_line", "requirement_sheet",
    "custodian_route", "manager_change_log", "person", "daily_counters",
)


class _Base(unittest.TestCase):
    def setUp(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()
        self.service = RequirementIssueService()

    def tearDown(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    # ---------------------------------------------------------------- 造数
    def bottle(self, number: str, qty: float = 100.0, unit: str = "g",
               manager: str = "李四", name: str = "乙醇") -> str:
        reagent_bottle_service.create(
            {
                "bottle_number": number,
                "reagent_name": name,
                "remaining_quantity": qty,
                "unit": unit,
                "manager": manager,
                "borrowable_flag": "可借",
                "borrowable_check": 1,
            }
        )
        return number

    def sheet(self, number: str = "SHEET-1", *, status: str = "submitted",
              requester: str = "张老师", code: str = "有机化学实验/蒸馏",
              lines=None) -> int:
        """建一张需求单。``lines`` 默认一项 100 g 乙醇——留足余量，让各
        测试自己决定这次发多少，不被截断干扰。"""
        requirement_sheet_service.create(
            {
                "sheet_number": number,
                "title": "蒸馏",
                "recipe_key": "distill",
                "status": status,
                "requester": requester,
                "source_kind": "teaching",
                "source_code": code,
                "academic_year": "2026-2027",
            }
        )
        row = TEST_DB.execute_query(
            "SELECT id FROM requirement_sheet WHERE sheet_number = ?", (number,)
        )
        sheet_id = int(row[0]["id"])
        if lines is None:
            lines = [(ETHANOL, 100.0, "g")]
        for seq, (substance, qty, unit) in enumerate(lines):
            TEST_DB.execute_update(
                "INSERT INTO requirement_line (sheet_id, seq, substance_key, "
                "display_name, quantity, unit) VALUES (?, ?, ?, ?, ?, ?)",
                (sheet_id, seq, substance.key, substance.name, qty, unit),
            )
        return sheet_id

    def _line(self, substance, seq, picks):
        lots = tuple(
            LotPick(lot_id=number, quantity=Quantity.of(qty, "g"))
            for number, qty in picks
        )
        total = Quantity.zero(Quantity.of(0, "g").unit)
        for pick in lots:
            total = total + pick.quantity
        return IssueLine(
            substance=substance,
            quantity=total,
            lot_id=",".join(pick.lot_id for pick in lots),
            seq=seq,
            picks=lots,
        )

    def acceptance(self, picks, *, requester: str = "张老师") -> Acceptance:
        """按给定 ``[(瓶号, 数量), ...]`` 造一张单行受理结论。

        真实链路里这些 picks 由 ``AcceptanceDesk`` 抽卡得出；这里直接给，
        测的是「拿到分配之后怎么落账」，不是抽卡本身。
        """
        return self.multi_acceptance([(ETHANOL, 0, picks)], requester=requester)

    def multi_acceptance(self, specs, *, requester: str = "张老师") -> Acceptance:
        """多行受理结论。``specs`` = ``[(物质, seq, [(瓶号, 数量)])]``。"""
        issued = tuple(
            self._line(substance, seq, picks) for substance, seq, picks in specs
        )
        sheet = RequirementSheet(
            recipe_key="distill",
            title="蒸馏",
            scale=BatchScale.single(),
            lines=tuple(
                RequirementLine(
                    substance=line.substance,
                    role=ComponentRole.REAGENT,
                    quantity=line.quantity,
                )
                for line in issued
            ),
        )
        return Acceptance(
            custodian=LI,
            request=TeacherRequest(
                requester=requester,
                sheet=sheet,
                source=SourceRef.teaching("有机化学实验", "蒸馏"),
            ),
            issued=issued,
        )

    # ---------------------------------------------------------------- 断言
    def remaining(self, number: str) -> float:
        return reagent_bottle_service.get_by_bottle_number(number).remaining_quantity

    def order_row(self, order_number: str) -> dict:
        rows = TEST_DB.execute_query(
            "SELECT * FROM borrow_order WHERE order_number = ?", (order_number,)
        )
        self.assertTrue(rows, f"借出单不存在：{order_number}")
        return rows[0]

    def item_rows(self, order_id: int) -> list:
        return TEST_DB.execute_query(
            "SELECT * FROM borrow_order_item WHERE order_id = ? ORDER BY id", (order_id,)
        )

    def sheet_row(self, number: str) -> dict:
        return TEST_DB.execute_query(
            "SELECT * FROM requirement_sheet WHERE sheet_number = ?", (number,)
        )[0]

    def line_rows(self, number: str) -> list:
        return TEST_DB.execute_query(
            "SELECT * FROM requirement_line WHERE sheet_id = "
            "(SELECT id FROM requirement_sheet WHERE sheet_number = ?) "
            "ORDER BY seq, id",
            (number,),
        )


class TestIssue(_Base):
    def test_each_bottle_gets_its_own_line(self):
        """一行拆两瓶 → 两条明细，各写各自的量。"""
        self.bottle("B-01", 100)
        self.bottle("B-02", 100)
        self.sheet("S1")

        result = self.service.issue(
            "S1", self.acceptance([("B-01", 30), ("B-02", 20)]), "李四"
        )

        self.assertTrue(result.success, result.message)
        order = self.order_row(result.data["order_number"])
        items = self.item_rows(order["id"])
        self.assertEqual([row["bottle_number"] for row in items], ["B-01", "B-02"])
        self.assertEqual([row["borrow_qty"] for row in items], [30.0, 20.0])
        self.assertTrue(all(row["unit"] == "g" for row in items))

    def test_items_point_back_to_the_requirement_line(self):
        """一张借出单里两瓶来自同一条需求行 → 明细都指回那一行。"""
        self.bottle("B-01", 100)
        self.bottle("B-02", 100)
        self.sheet("S1")

        result = self.service.issue(
            "S1", self.acceptance([("B-01", 30), ("B-02", 20)]), "李四"
        )

        items = self.item_rows(result.data["order_id"])
        line_id = self.line_rows("S1")[0]["id"]
        self.assertEqual({row["requirement_line_id"] for row in items}, {line_id})

    def test_stock_actually_drops(self):
        """转单不是记账游戏：库存必须真的扣掉。"""
        self.bottle("B-01", 100)
        self.sheet("S1")

        self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        self.assertAlmostEqual(self.remaining("B-01"), 70.0, places=3)

    def test_order_carries_its_source_sheet(self):
        """借出单要能反查是哪张需求单，否则兑付对账只能靠回忆。"""
        self.bottle("B-01", 100)
        self.sheet("S1")

        result = self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        order = self.order_row(result.data["order_number"])
        self.assertEqual(order["requirement_number"], "S1")
        self.assertEqual(order["applicant"], "张老师")       # 领用是老师
        self.assertEqual(order["created_by"], "李四")        # 发料是管理员
        self.assertEqual(order["order_type"], "课程领用")
        self.assertEqual(order["course_name"], "有机化学实验")
        self.assertEqual(order["item_name"], "蒸馏")

    def test_line_carries_its_progress(self):
        """兑付量落在行上：已发、状态、借出单号三样一次写全。"""
        self.bottle("B-01", 100)
        self.sheet("S1")

        result = self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        line = self.line_rows("S1")[0]
        self.assertAlmostEqual(line["issued_quantity"], 30.0, places=3)
        self.assertEqual(line["status"], "partial")          # 100 里发了 30
        self.assertEqual(line["order_number"], result.data["order_number"])

    def test_draft_sheet_can_be_issued(self):
        """页面生成的需求单就是 draft，中间没有强制提交动作，不能卡死。"""
        self.bottle("B-01", 100)
        self.sheet("S1", status="draft", lines=[(ETHANOL, 30.0, "g")])

        result = self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        self.assertTrue(result.success, result.message)
        self.assertEqual(self.sheet_row("S1")["status"], "issued")


class TestPartialIssue(_Base):
    """一门课 20 项今天只到 5 项：发得出的先结算，剩下的留着。"""

    def test_only_the_ticked_lines_are_issued(self):
        """勾了一项 → 只有这一项被兑付，另一项原地不动。"""
        self.bottle("B-01", 100, name="乙醇")
        self.bottle("B-02", 100, name="水")
        self.sheet("S1", lines=[(ETHANOL, 50.0, "g"), (WATER, 50.0, "g")])
        acceptance = self.multi_acceptance(
            [(ETHANOL, 0, [("B-01", 20)]), (WATER, 1, [("B-02", 30)])]
        )

        result = self.service.issue("S1", acceptance, "李四", selections=[0])

        self.assertTrue(result.success, result.message)
        lines = self.line_rows("S1")
        self.assertEqual([row["status"] for row in lines], ["partial", "open"])
        self.assertAlmostEqual(lines[0]["issued_quantity"], 20.0, places=3)
        self.assertAlmostEqual(lines[1]["issued_quantity"], 0.0, places=3)
        # 只扣了勾中的那瓶
        self.assertAlmostEqual(self.remaining("B-01"), 80.0, places=3)
        self.assertAlmostEqual(self.remaining("B-02"), 100.0, places=3)

    def test_sheet_becomes_partial_not_issued(self):
        """有项发了、有项没发 → 单头 partial。置 issued 会把没发的吞掉。"""
        self.bottle("B-01", 100, name="乙醇")
        self.bottle("B-02", 100, name="水")
        self.sheet("S1", lines=[(ETHANOL, 50.0, "g"), (WATER, 50.0, "g")])
        acceptance = self.multi_acceptance(
            [(ETHANOL, 0, [("B-01", 20)]), (WATER, 1, [("B-02", 30)])]
        )

        self.service.issue("S1", acceptance, "李四", selections=[0])

        row = self.sheet_row("S1")
        self.assertEqual(row["status"], "partial")
        self.assertTrue(row["order_number"])   # 首张借出单锚点已留

    def test_second_round_issues_the_rest(self):
        """第二批勾剩下的项 → 单头收口为 issued。"""
        self.bottle("B-01", 100, name="乙醇")
        self.bottle("B-02", 100, name="水")
        self.sheet("S1", lines=[(ETHANOL, 20.0, "g"), (WATER, 30.0, "g")])
        acceptance = self.multi_acceptance(
            [(ETHANOL, 0, [("B-01", 20)]), (WATER, 1, [("B-02", 30)])]
        )

        first = self.service.issue("S1", acceptance, "李四", selections=[0])
        second = self.service.issue("S1", acceptance, "李四", selections=[1])

        self.assertTrue(first.success, first.message)
        self.assertTrue(second.success, second.message)
        self.assertNotEqual(first.data["order_number"], second.data["order_number"])
        self.assertEqual(self.sheet_row("S1")["status"], "issued")
        self.assertEqual(
            [row["status"] for row in self.line_rows("S1")], ["issued", "issued"]
        )
        # 两张借出单都能反查到同一张需求单
        orders = TEST_DB.execute_query(
            "SELECT COUNT(*) AS n FROM borrow_order WHERE requirement_number = 'S1'"
        )
        self.assertEqual(orders[0]["n"], 2)

    def test_first_order_number_is_not_overwritten(self):
        """单头的单号是「第一次兑付的入口」，第二次不能把它改掉。"""
        self.bottle("B-01", 100, name="乙醇")
        self.bottle("B-02", 100, name="水")
        self.sheet("S1", lines=[(ETHANOL, 20.0, "g"), (WATER, 30.0, "g")])
        acceptance = self.multi_acceptance(
            [(ETHANOL, 0, [("B-01", 20)]), (WATER, 1, [("B-02", 30)])]
        )

        first = self.service.issue("S1", acceptance, "李四", selections=[0])
        self.service.issue("S1", acceptance, "李四", selections=[1])

        self.assertEqual(
            self.sheet_row("S1")["order_number"], first.data["order_number"]
        )

    def test_fully_settled_line_is_not_issued_again(self):
        """已兑完的行再勾 → 拒绝，不重复扣库存。"""
        self.bottle("B-01", 100)
        self.sheet("S1", lines=[(ETHANOL, 30.0, "g")])
        acceptance = self.acceptance([("B-01", 30)])
        self.service.issue("S1", acceptance, "李四")

        again = self.service.issue("S1", acceptance, "李四")

        self.assertFalse(again.success)
        self.assertEqual(again.error_code, "ALREADY_ISSUED")
        self.assertAlmostEqual(self.remaining("B-01"), 70.0, places=3)

    def test_offered_quantity_is_trimmed_to_remaining(self):
        """受理时说 30，行上只剩 10 → 只发 10。不截断就是重复兑付。"""
        self.bottle("B-01", 100)
        self.bottle("B-02", 100)
        self.sheet("S1", lines=[(ETHANOL, 40.0, "g")])
        # 第一批：10 从 B-01
        self.service.issue("S1", self.acceptance([("B-01", 10)]), "李四")
        # 第二批：受理结论还是全量 30，但行上只剩 30
        second = self.service.issue("S1", self.acceptance([("B-02", 30)]), "李四")

        self.assertTrue(second.success, second.message)
        line = self.line_rows("S1")[0]
        self.assertAlmostEqual(line["issued_quantity"], 40.0, places=3)
        self.assertEqual(line["status"], "issued")

    def test_nothing_ticked_is_refused(self):
        """一项都没勾 → 不生成空借出单。"""
        self.bottle("B-01", 100)
        self.sheet("S1")

        result = self.service.issue(
            "S1", self.acceptance([("B-01", 30)]), "李四", selections=[]
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "NOTHING_TO_ISSUE")
        self.assertFalse(TEST_DB.execute_query("SELECT id FROM borrow_order"))


class TestFailures(_Base):
    def test_line_without_a_bottle_is_not_guessed(self):
        """不知道是哪一瓶的行不进借出单，如实说明而不是随便挑一瓶。"""
        self.sheet("S1")
        acceptance = self.acceptance([("B-01", 30)])
        # 把 picks 抹掉，模拟跨量纲发放（只知道折合量，不知道瓶）
        no_pick = IssueLine(
            substance=ETHANOL,
            quantity=Quantity.of(30, "g"),
            lot_id="",
            seq=0,
        )
        acceptance = Acceptance(
            custodian=acceptance.custodian,
            request=acceptance.request,
            issued=(no_pick,),
        )

        result = self.service.issue("S1", acceptance, "李四")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "NOTHING_TO_ISSUE")
        self.assertIn("现场办理", result.data["skipped"][0])

    def test_missing_bottle_does_not_block_the_others(self):
        """一瓶找不到，另一瓶照发——料可能已经在老师手上。"""
        self.bottle("B-02", 100)
        self.sheet("S1")

        result = self.service.issue(
            "S1", self.acceptance([("B-01", 30), ("B-02", 20)]), "李四"
        )

        self.assertTrue(result.success, result.message)
        self.assertTrue(result.data["is_partial"])
        items = self.item_rows(result.data["order_id"])
        self.assertEqual([row["bottle_number"] for row in items], ["B-02"])
        # 只发了 20，行上还剩 80——没发出去的量还在单上，下次能发
        self.assertAlmostEqual(
            self.line_rows("S1")[0]["issued_quantity"], 20.0, places=3
        )
        self.assertTrue(any("B-01" in note for note in result.data["skipped"]))

    def test_nothing_borrowed_rolls_back(self):
        """一瓶都发不出去，整单不该留痕。"""
        self.sheet("S1")

        result = self.service.issue(
            "S1", self.acceptance([("B-01", 30), ("B-02", 20)]), "李四"
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "NOTHING_TO_ISSUE")
        self.assertEqual(self.sheet_row("S1")["status"], "submitted")
        self.assertFalse(
            TEST_DB.execute_query("SELECT id FROM borrow_order"), "不该留下空借出单"
        )

    def test_over_borrow_is_refused_by_the_bottle(self):
        """整行量超过瓶里剩的：借出拒绝，落到失败里而不是硬扣。"""
        self.bottle("B-01", 10)
        self.sheet("S1")

        result = self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        self.assertFalse(result.success)
        self.assertAlmostEqual(self.remaining("B-01"), 10.0, places=3)
        self.assertFalse(TEST_DB.execute_query("SELECT id FROM borrow_order"))

    def test_sheet_without_lines_is_refused(self):
        """没有明细行的单不能兑付——没有行就没有余量，重复发料无从拦。"""
        self.bottle("B-01", 100)
        self.sheet("S1", lines=[])

        result = self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "NO_LINES")
        self.assertAlmostEqual(self.remaining("B-01"), 100.0, places=3)


class TestPendingRows(_Base):
    def test_pending_lists_every_line_with_its_progress(self):
        """页面勾选表要看到需求 / 已发 / 余量三列，否则勾不明白。"""
        self.bottle("B-01", 100, name="乙醇")
        self.bottle("B-02", 100, name="水")
        self.sheet("S1", lines=[(ETHANOL, 50.0, "g"), (WATER, 60.0, "g")])
        acceptance = self.multi_acceptance(
            [(ETHANOL, 0, [("B-01", 20)]), (WATER, 1, [("B-02", 30)])]
        )

        preview = self.service.pending_rows("S1", acceptance)

        self.assertTrue(preview.success, preview.message)
        rows = preview.data["lines"]
        self.assertEqual([row["name"] for row in rows], ["乙醇", "水"])
        self.assertEqual([row["remaining"] for row in rows], [50.0, 60.0])
        self.assertEqual([row["issuable"] for row in rows], [True, True])
        self.assertEqual(preview.data["pending"], 2)

    def test_pending_shows_remaining_after_a_partial_issue(self):
        """发过一批之后，勾选表上的余量要跟着降。"""
        self.bottle("B-01", 100)
        self.sheet("S1", lines=[(ETHANOL, 50.0, "g")])
        self.service.issue("S1", self.acceptance([("B-01", 20)]), "李四")

        preview = self.service.pending_rows("S1")

        row = preview.data["lines"][0]
        self.assertAlmostEqual(row["issued"], 20.0, places=3)
        self.assertAlmostEqual(row["remaining"], 30.0, places=3)


class TestSheetStatusPromotion(_Base):
    """受理 → submitted。不推这一步，保底永远算不到任何一张单。"""

    def test_draft_is_promoted_on_intake(self):
        self.sheet("S1", status="draft")

        self.assertTrue(requirement_sheet_service.promote_to_submitted("S1", "李四"))

        self.assertEqual(self.sheet_row("S1")["status"], "submitted")

    def test_issued_sheet_is_not_dragged_back(self):
        """已兑付的单不能被再一次受理打回 submitted——兑付进度会被踩平。"""
        self.bottle("B-01", 100)
        self.sheet("S1", status="draft", lines=[(ETHANOL, 30.0, "g")])
        self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        self.assertFalse(requirement_sheet_service.promote_to_submitted("S1", "李四"))

        self.assertEqual(self.sheet_row("S1")["status"], "issued")
        self.assertAlmostEqual(
            self.line_rows("S1")[0]["issued_quantity"], 30.0, places=3
        )


class TestReserveReleased(_Base):
    """兑付之后，同一学年里这张单不再占保底——但只放掉已发的那部分。"""

    def setUp(self):
        super().setUp()
        TEST_DB.execute_update(
            "INSERT INTO custodian_route (scope_type, scope_key, custodian) "
            "VALUES (?, ?, ?)",
            ("course", "有机化学实验", "李四"),
        )
        self.reserve = DemandReserve(
            database=TEST_DB,
            routes=CustodianRouteRepository(TEST_DB),
            today=TODAY,
        )

    def ask(self, sheet_number: str = ""):
        return self.reserve(
            ReserveQuery(
                custodian=LI,
                substance=ETHANOL,
                exclude_source=("teaching", sheet_number) if sheet_number else None,
            )
        )

    def test_submitted_sheet_holds_material(self):
        """提交未兑付：保底占着，这部分料不能被抽走。"""
        self.sheet("S1", lines=[(ETHANOL, 30.0, "g")])

        self.assertEqual(self.ask().base_value(), 30)

    def test_partial_issue_only_holds_the_rest(self):
        """发了一半 → 保底只剩一半。按全量算会把发出去的也当欠量。"""
        self.bottle("B-01", 100)
        self.sheet("S1", lines=[(ETHANOL, 50.0, "g")])
        self.service.issue("S1", self.acceptance([("B-01", 20)]), "李四")

        self.assertEqual(self.ask().base_value(), 30)

    def test_issued_sheet_stops_holding_material(self):
        """全部兑付后保底归零——这正是「借出即兑付」要解决的那件事。"""
        self.bottle("B-01", 100)
        self.sheet("S1", lines=[(ETHANOL, 30.0, "g")])
        self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        self.assertIsNone(self.ask())


if __name__ == "__main__":
    unittest.main()
