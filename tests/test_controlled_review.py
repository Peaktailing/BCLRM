"""管制试剂双人审批。

守三条不变量：

1. **两签之间库存不动** —— 一审只签字，二审才出库。先发再补签，签的是已经
   发生的事，双人审批就成了事后追认。
2. **第二签不能是自己** —— 一个人点两次不叫两个人看过。
3. **需求单先复核后兑付** —— 兑付即发料，复核必须排在它前面。

工单与需求单两条入口共用同一套判定口径（CAS → 名称 → 别名），否则同一瓶
试剂走工单要两签、走需求单却一签，规矩等于没有。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from tests.test_requirement_issue import ETHANOL, _Base as _IssueBase

from business.requirement_review_service import RequirementReviewService
from business.work_order_service import work_order_service
from domain.substance import SubstanceRef
from services.base.controlled_list_service import controlled_list_service
from services.base.person_service import person_service
from services.core.borrow_order_service import (
    borrow_order_item_service,
    borrow_order_service,
)
from services.core.reagent_bottle_service import reagent_bottle_service

ETHER = SubstanceRef.of("乙醚")

_TABLES = (
    "borrow_order_item", "borrow_order", "borrow_record", "return_record",
    "reagent_bottle", "requirement_line", "requirement_sheet",
    "controlled_list", "person", "operation_log",
)


def _reset():
    for table in _TABLES:
        try:
            TEST_DB.connection.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    TEST_DB.connection.commit()


def _person(name: str, role: str = "admin", department: str = "") -> str:
    TEST_DB.connection.execute(
        "INSERT OR IGNORE INTO person (name, role, department) VALUES (?, ?, ?)",
        (name, role, department),
    )
    TEST_DB.connection.commit()
    return name


def _controlled(name: str, cas: str, kind: str = "易制毒") -> None:
    """名录是全局表，测试库与其他用例共享——重复插入会撞唯一索引。"""
    exists = TEST_DB.execute_query(
        "SELECT id FROM controlled_list WHERE chemical_name = ? AND cas_number = ?",
        (name, cas),
    )
    if exists:
        return
    controlled_list_service.create({
        "chemical_name": name,
        "cas_number": cas,
        "dangerous_type": kind,
    })


class TestWorkOrderTwoSign(unittest.TestCase):
    """工单：一审 → 待复核 → 二审 → 出库。"""

    def setUp(self):
        _reset()
        _person("王管理员")
        _person("李管理员")
        _person("李老师", role="teacher")
        _controlled("乙醚", "CN-ETHER")
        reagent_bottle_service.create({
            "bottle_number": "B7001",
            "reagent_name": "乙醚",
            "cas_number": "CN-ETHER",
            "remaining_quantity": 100.0,
            "borrowable_flag": "可借",
            "expired_flag": "正常",
        })
        self.order_id = self._make_order()

    def tearDown(self):
        _reset()

    def _make_order(self) -> int:
        order_id = borrow_order_service.create({
            "order_number": "CTRL-0001",
            "order_type": "零星领用",
            "applicant": "李老师",
            "status": "待审批",
            "approval_status": "待审批",
            "approver": "王管理员",
            "controlled_flag": 1,
        })
        borrow_order_item_service.create({
            "order_id": order_id,
            "bottle_number": "B7001",
            "reagent_name": "乙醚",
            "borrow_qty": 10.0,
            "returned_qty": 0.0,
            "unit": "g",
            "status": "待归还",
        })
        return order_id

    def _stock(self) -> float:
        return float(
            reagent_bottle_service.get_by_bottle_number("B7001").remaining_quantity
        )

    def test_first_sign_does_not_touch_stock(self):
        result = work_order_service.approve_order(
            self.order_id, "王管理员", "同意", second_approver="李管理员"
        )
        self.assertTrue(result.is_success(), result.message)

        order = borrow_order_service.get_by_id(self.order_id)
        self.assertEqual(order.approval_status, "待复核")
        self.assertEqual(order.second_approver, "李管理员")
        self.assertEqual(order.approver, "王管理员")
        self.assertAlmostEqual(self._stock(), 100.0, msg="一审不许动库存")

    def test_second_sign_executes_borrow(self):
        work_order_service.approve_order(
            self.order_id, "王管理员", second_approver="李管理员"
        )
        result = work_order_service.approve_second(self.order_id, "李管理员")
        self.assertTrue(result.is_success(), result.message)

        order = borrow_order_service.get_by_id(self.order_id)
        self.assertEqual(order.approval_status, "已批准")
        self.assertEqual(order.second_approval_status, "已复核")
        # 两个签名各归各位：第二签不改第一签的人
        self.assertEqual(order.approver, "王管理员")
        self.assertAlmostEqual(self._stock(), 90.0)

    def test_reviewer_cannot_be_the_first_signer(self):
        result = work_order_service.approve_order(
            self.order_id, "王管理员", second_approver="王管理员"
        )
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, "SAME_SECOND_APPROVER")
        self.assertAlmostEqual(self._stock(), 100.0)

    def test_reviewer_cannot_be_the_applicant(self):
        result = work_order_service.approve_order(
            self.order_id, "王管理员", second_approver="李老师"
        )
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, "APPLICANT_CANNOT_REVIEW")

    def test_reviewer_must_be_an_admin(self):
        _person("路人甲", role="teacher")
        result = work_order_service.approve_order(
            self.order_id, "王管理员", second_approver="路人甲"
        )
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, "INVALID_SECOND_APPROVER")

    def test_second_sign_is_reserved_to_the_designated_person(self):
        work_order_service.approve_order(
            self.order_id, "王管理员", second_approver="李管理员"
        )
        result = work_order_service.approve_second(self.order_id, "王管理员")
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, "NOT_SECOND_APPROVER")
        self.assertAlmostEqual(self._stock(), 100.0)

    def test_rejection_at_second_sign_closes_order_without_stock_change(self):
        work_order_service.approve_order(
            self.order_id, "王管理员", second_approver="李管理员"
        )
        result = work_order_service.reject_order(self.order_id, "李管理员")
        self.assertTrue(result.is_success(), result.message)

        order = borrow_order_service.get_by_id(self.order_id)
        self.assertEqual(order.approval_status, "已驳回")
        self.assertEqual(order.second_approval_status, "已驳回")
        self.assertAlmostEqual(self._stock(), 100.0)

    def test_reviewer_sees_order_in_their_todo(self):
        work_order_service.approve_order(
            self.order_id, "王管理员", second_approver="李管理员"
        )
        mine = work_order_service.list_pending_approvals("李管理员")
        self.assertEqual([o.order_number for o in mine], ["CTRL-0001"])
        # 第一签的人已经交棒，不再挂在他名下
        self.assertEqual(work_order_service.list_pending_approvals("王管理员"), [])


class TestRequirementReview(_IssueBase):
    """需求单：送复核 → 复核通过 → 才允许兑付。"""

    def setUp(self):
        super().setUp()
        _person("王管理员")
        _person("李管理员")
        _controlled("乙醚", "CN-ETHER")
        self.review = RequirementReviewService()

    def _ether_sheet(self, number="SHEET-CTRL"):
        return self.sheet(number, lines=[(ETHER, 100.0, "g")])

    def test_controlled_issue_blocked_without_review(self):
        self.bottle("B6001", name="乙醚")
        self._ether_sheet()
        result = self.service.issue(
            "SHEET-CTRL", self.multi_acceptance([(ETHER, 0, [("B6001", 10.0)])]), operator="王管理员"
        )
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, "CONTROLLED_REVIEW_REQUIRED")

    def test_issue_allowed_after_review(self):
        self.bottle("B6002", name="乙醚")
        self._ether_sheet()
        sent = self.review.request("SHEET-CTRL", "王管理员", "李管理员")
        self.assertTrue(sent.is_success(), sent.message)
        approved = self.review.approve("SHEET-CTRL", "李管理员")
        self.assertTrue(approved.is_success(), approved.message)

        result = self.service.issue(
            "SHEET-CTRL", self.multi_acceptance([(ETHER, 0, [("B6002", 10.0)])]), operator="王管理员"
        )
        self.assertTrue(result.is_success(), result.message)

    def test_review_is_consumed_after_issue(self):
        """一轮一签：这批发完，下一批要重新送复核。"""
        self.bottle("B6003", name="乙醚")
        self._ether_sheet()
        self.review.request("SHEET-CTRL", "王管理员", "李管理员")
        self.review.approve("SHEET-CTRL", "李管理员")
        self.service.issue(
            "SHEET-CTRL", self.multi_acceptance([(ETHER, 0, [("B6003", 10.0)])]), operator="王管理员"
        )

        row = TEST_DB.execute_query(
            "SELECT second_approval_status FROM requirement_sheet "
            "WHERE sheet_number = 'SHEET-CTRL'"
        )[0]
        self.assertEqual(row["second_approval_status"] or "", "")

    def test_review_rejects_self_and_non_admin(self):
        self._ether_sheet()
        same = self.review.request("SHEET-CTRL", "王管理员", "王管理员")
        self.assertFalse(same.is_success())
        self.assertEqual(same.error_code, "SAME_SECOND_APPROVER")

        _person("路人甲", role="teacher")
        bad = self.review.request("SHEET-CTRL", "王管理员", "路人甲")
        self.assertFalse(bad.is_success())
        self.assertEqual(bad.error_code, "INVALID_SECOND_APPROVER")

    def test_only_designated_reviewer_can_approve(self):
        self._ether_sheet()
        self.review.request("SHEET-CTRL", "王管理员", "李管理员")
        result = self.review.approve("SHEET-CTRL", "王管理员")
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, "NOT_SECOND_APPROVER")

    def test_pending_review_shows_in_reviewer_list(self):
        self._ether_sheet()
        self.review.request("SHEET-CTRL", "王管理员", "李管理员")
        self.assertEqual(
            [r["sheet_number"] for r in self.review.pending_for("李管理员")],
            ["SHEET-CTRL"],
        )
        self.assertEqual(self.review.pending_for("王管理员"), [])

    def test_uncontrolled_sheet_needs_no_review(self):
        """不含管控的单不该被拦：双人审批只针对管制试剂。"""
        self.bottle("B6004", name="乙醇")
        self.sheet("SHEET-PLAIN")
        result = self.service.issue(
            "SHEET-PLAIN", self.acceptance([("B6004", 10.0)]), operator="王管理员"
        )
        self.assertTrue(result.is_success(), result.message)


if __name__ == "__main__":
    unittest.main()
