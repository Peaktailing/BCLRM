"""保底：本学年该保管人还没兑现的用量。

三条边界各有一个用例：跨学年不算、同源不算、别人的范围不算。这三条
只要错一条，结局都一样——某个老师的料永远抽不出来。
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from capabilities.circulation.picking import ReserveQuery
from domain.custody import Custodian
from domain.substance import SubstanceRef
from services.custodian_route import CustodianRouteRepository
from services.demand_reserve import DemandReserve

ETHANOL = SubstanceRef.of("乙醇")
TODAY = date(2026, 10, 23)          # 属于 2026-2027 学年
LI = Custodian("李四")
WANG = Custodian("王五")


class _ReserveBase(unittest.TestCase):
    def setUp(self):
        for table in ("requirement_line", "requirement_sheet", "custodian_route"):
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()
        self.reserve = DemandReserve(
            database=TEST_DB,
            routes=CustodianRouteRepository(TEST_DB),
            today=TODAY,
        )

    # ---------------------------------------------------------------- 造数
    def route(self, scope_type: str, scope_key: str, custodian: str):
        TEST_DB.execute_update(
            "INSERT INTO custodian_route (scope_type, scope_key, custodian) "
            "VALUES (?, ?, ?)",
            (scope_type, scope_key, custodian),
        )

    def sheet(self, number: str, code: str, *, semester="2026-2027",
              kind="teaching", status="submitted", quantity=30.0,
              unit="g", substance=None) -> int:
        TEST_DB.execute_update(
            "INSERT INTO requirement_sheet "
            "(sheet_number, title, status, source_kind, source_code, academic_year) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (number, code, status, kind, code, semester),
        )
        row = TEST_DB.execute_query(
            "SELECT id FROM requirement_sheet WHERE sheet_number = ?", (number,)
        )
        sheet_id = int(row[0]["id"])
        TEST_DB.execute_update(
            "INSERT INTO requirement_line "
            "(sheet_id, seq, substance_key, display_name, quantity, unit) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sheet_id, 0, (substance or ETHANOL).key, "乙醇", quantity, unit),
        )
        return sheet_id

    def ask(self, query=None):
        return self.reserve(query or ReserveQuery(custodian=LI, substance=ETHANOL))


class TestScope(_ReserveBase):
    def test_no_route_means_no_reserve(self):
        """没配路由就不知道该保谁的量：返回 None，不锁料。"""
        self.sheet("S1", "有机化学实验/蒸馏")
        self.assertIsNone(self.ask())

    def test_course_scope_covers_its_items(self):
        """路由配的是课程名，单上是「课程/实验」，应当命中。"""
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏")
        self.assertEqual(self.ask().base_value(), 30)

    def test_course_class_scope_needs_the_class(self):
        """配到班级粒度的规则不会误伤别的班。"""
        self.route("course_class", "有机化学实验/应化2301", "李四")
        self.sheet("S1", "有机化学实验/应化2302")
        self.assertIsNone(self.ask())

    def test_other_custodian_scope_is_ignored(self):
        self.route("course", "分析化学实验", "王五")
        self.sheet("S1", "分析化学实验/滴定")
        self.assertIsNone(self.ask())

    def test_multiple_sheets_accumulate(self):
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", quantity=30)
        self.sheet("S2", "有机化学实验/萃取", quantity=20)
        self.assertEqual(self.ask().base_value(), 50)

    def test_other_substance_is_ignored(self):
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", substance=SubstanceRef.of("丙酮"))
        self.assertIsNone(self.ask())


class TestYearBoundary(_ReserveBase):
    def test_previous_year_does_not_count(self):
        """一年一轮：去年的单不该压着今年的料。"""
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", semester="2025-2026")
        self.assertIsNone(self.ask())

    def test_current_year_counts(self):
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", semester="2026-2027")
        self.assertEqual(self.ask().base_value(), 30)

    def test_next_year_does_not_count_yet(self):
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", semester="2027-2028")
        self.assertIsNone(self.ask())


class TestStatus(_ReserveBase):
    def test_draft_does_not_reserve(self):
        """草稿是老师还没想好的，不该占料。"""
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", status="draft")
        self.assertIsNone(self.ask())

    def test_submitted_reserves(self):
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", status="submitted")
        self.assertEqual(self.ask().base_value(), 30)


class TestExcludeSource(_ReserveBase):
    def test_same_source_is_excluded(self):
        """当前这张单不能把自己算成保底，否则永远抽不出来。"""
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", quantity=50)
        query = ReserveQuery(
            custodian=LI,
            substance=ETHANOL,
            exclude_source=("teaching", "有机化学实验/蒸馏"),
        )
        self.assertIsNone(self.ask(query))

    def test_other_source_still_counts(self):
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", quantity=50)
        self.sheet("S2", "有机化学实验/萃取", quantity=20)
        query = ReserveQuery(
            custodian=LI,
            substance=ETHANOL,
            exclude_source=("teaching", "有机化学实验/蒸馏"),
        )
        self.assertEqual(self.ask(query).base_value(), 20)


class TestDimension(_ReserveBase):
    def test_reserve_keeps_its_own_dimension(self):
        """保底量按单据的量纲给出，不做折算；对不上需求时由抽卡层挡掉。"""
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", unit="mL", quantity=100)
        reserved = self.ask()
        self.assertEqual(reserved.base_value(), 100)
        self.assertEqual(reserved.unit.symbol, "mL")

    def test_mixed_dimensions_are_not_added_together(self):
        """跨量纲相加没有意义，只累计第一种量纲的行。"""
        self.route("course", "有机化学实验", "李四")
        self.sheet("S1", "有机化学实验/蒸馏", unit="g", quantity=30)
        self.sheet("S2", "有机化学实验/萃取", unit="mL", quantity=100)
        reserved = self.ask()
        self.assertEqual(reserved.unit.dimension.label, "质量")

        query = ReserveQuery(custodian=LI, substance=ETHANOL)
        self.assertEqual(self.ask(query).base_value(), 30)


if __name__ == "__main__":
    unittest.main()
