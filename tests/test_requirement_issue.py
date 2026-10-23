"""需求单转借出单：借出即兑付。

测三件事，每件都对应一个会真实发生的坏结果：

1. **逐瓶落单** —— 一行拆两瓶时，明细必须写清「这瓶扣多少」。写成
   「A、B 共 50 g」的账，扣库存时只能猜。
2. **借出即兑付** —— 料发了、需求单还挂在 submitted，同一学年里第二次
   申领就被自己上一张单压住（v0.9.4 留下的缺口）。
3. **失败不乱账** —— 一瓶发不出去时，已发的照常落单，需求单照样兑付；
   一瓶都发不出去时整单回滚，不留半截。
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
              requester: str = "张老师", code: str = "有机化学实验/蒸馏") -> int:
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
        return int(row[0]["id"])

    def acceptance(self, picks, *, requester: str = "张老师") -> Acceptance:
        """按给定 ``[(瓶号, 数量), ...]`` 造一张受理结论。

        真实链路里这些 picks 由 ``AcceptanceDesk`` 抽卡得出；这里直接给，
        测的是「拿到分配之后怎么落账」，不是抽卡本身。
        """
        lots = tuple(
            LotPick(lot_id=number, quantity=Quantity.of(qty, "g"))
            for number, qty in picks
        )
        total = Quantity.zero(Quantity.of(0, "g").unit)
        for pick in lots:
            total = total + pick.quantity
        line = IssueLine(
            substance=ETHANOL,
            quantity=total,
            lot_id=",".join(pick.lot_id for pick in lots),
            seq=0,
            picks=lots,
        )
        sheet = RequirementSheet(
            recipe_key="distill",
            title="蒸馏",
            scale=BatchScale.single(),
            lines=(
                RequirementLine(
                    substance=ETHANOL,
                    role=ComponentRole.REAGENT,
                    quantity=total,
                ),
            ),
        )
        return Acceptance(
            custodian=LI,
            request=TeacherRequest(
                requester=requester,
                sheet=sheet,
                source=SourceRef.teaching("有机化学实验", "蒸馏"),
            ),
            issued=(line,),
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

    def test_sheet_is_settled_in_the_same_move(self):
        """借出即兑付：状态、单号、时刻、发料人一次写全。"""
        self.bottle("B-01", 100)
        self.sheet("S1")

        result = self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        row = self.sheet_row("S1")
        self.assertEqual(row["status"], "issued")
        self.assertEqual(row["order_number"], result.data["order_number"])
        self.assertEqual(row["issued_by"], "李四")
        self.assertTrue(row["issued_at"])

    def test_second_issue_is_refused(self):
        """同一张单不能兑付两次——第二次是重复发料。"""
        self.bottle("B-01", 100)
        self.sheet("S1")
        self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        again = self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        self.assertFalse(again.success)
        self.assertEqual(again.error_code, "ALREADY_ISSUED")
        self.assertAlmostEqual(self.remaining("B-01"), 70.0, places=3)

    def test_draft_sheet_can_be_issued(self):
        """页面生成的需求单就是 draft，中间没有强制提交动作，不能卡死。"""
        self.bottle("B-01", 100)
        self.sheet("S1", status="draft")

        result = self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        self.assertTrue(result.success, result.message)
        self.assertEqual(self.sheet_row("S1")["status"], "issued")


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
        # 需求单仍然兑付：受理已完成，剩下的是缺口，由第二段/采购接手
        self.assertEqual(self.sheet_row("S1")["status"], "issued")
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


class TestReserveReleased(_Base):
    """兑付之后，同一学年里这张单不再占保底。"""

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
        self.bottle("B-01", 100)
        self.sheet("S1")
        TEST_DB.execute_update(
            "INSERT INTO requirement_line (sheet_id, seq, substance_key, display_name, "
            "quantity, unit) VALUES ((SELECT id FROM requirement_sheet WHERE "
            "sheet_number='S1'), 0, ?, '乙醇', 30.0, 'g')",
            (ETHANOL.key,),
        )

        self.assertEqual(self.ask().base_value(), 30)

    def test_issued_sheet_stops_holding_material(self):
        """兑付之后保底归零——这正是「借出即兑付」要解决的那件事。"""
        self.bottle("B-01", 100)
        self.sheet("S1")
        TEST_DB.execute_update(
            "INSERT INTO requirement_line (sheet_id, seq, substance_key, display_name, "
            "quantity, unit) VALUES ((SELECT id FROM requirement_sheet WHERE "
            "sheet_number='S1'), 0, ?, '乙醇', 30.0, 'g')",
            (ETHANOL.key,),
        )
        self.service.issue("S1", self.acceptance([("B-01", 30)]), "李四")

        self.assertIsNone(self.ask())


if __name__ == "__main__":
    unittest.main()
