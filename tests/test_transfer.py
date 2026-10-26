"""调配台：缺口 → 建议 → 对方点头 → 平账。

测的都是会真实发生的坏结果：

1. **受益人自己点头** —— 调的是出料人的保管权，他自己答应了就等于替人做主。
2. **双击同意** —— 第二次必须被 CAS 挡住，不能把已流转的账再流转一遍。
3. **一瓶都没转成** —— 单不能停在「已同意」：账上生效了、实际没人拿到料。
4. **在借瓶** —— 人在外面拿着货时不能把责任转给别人。
5. **拒绝不写理由** —— 对方不知道是「没有」还是「不给」，只能干等。
6. **一行要动两瓶** —— 明细必须拆到瓶，否则执行时扣哪瓶扣多少全靠猜。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.substance import SubstanceRef
from domain.transfer import (
    ANSWER_NO_SELECTION,
    ANSWER_REMARK_REQUIRED,
    ANSWER_SELF,
    ITEM_DECLINED,
    ITEM_PENDING,
    TRANSFER_ACCEPTED,
    TRANSFER_REJECTED,
    TRANSFER_REQUESTED,
    can_answer,
    can_cancel,
    can_reject,
    check_parties,
    resolve_selections,
)
from business.transfer_service import TransferService
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.requirement_sheet_service import requirement_sheet_service
from services.core.transfer_order_service import transfer_order_service
from tests import TEST_DB

ETHANOL = SubstanceRef.of("乙醇")
ME = "王五"        # 受益人（缺料的管理员）
LI = "李四"        # 出料人
ZHAO = "赵六"      # 另一个出料人
TEACHER = "张老师"

_TABLES = (
    "transfer_order_item", "transfer_order", "borrow_order_item", "borrow_order",
    "borrow_record", "return_record", "reagent_bottle", "requirement_line",
    "requirement_sheet", "custodian_route", "manager_change_log", "person",
    "daily_counters", "work_group", "work_group_member",
)


class _Base(unittest.TestCase):
    def setUp(self):
        self._clean()
        for name in (ME, LI, ZHAO, TEACHER):
            self.person(name)
        self.service = TransferService()

    def tearDown(self):
        self._clean()

    @staticmethod
    def _clean():
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    # ---------------------------------------------------------------- 造数
    @staticmethod
    def person(name: str, role: str = "admin", department: str = "化学教研室") -> None:
        TEST_DB.execute_update(
            "INSERT OR IGNORE INTO person (name, password_hash, role, department) "
            "VALUES (?, ?, ?, ?)",
            (name, "x", role, department),
        )

    def bottle(self, number: str, qty: float, manager: str, unit: str = "g",
               borrowable: str = "可借") -> str:
        reagent_bottle_service.create(
            {
                "bottle_number": number,
                "reagent_name": "乙醇",
                "remaining_quantity": qty,
                "unit": unit,
                "manager": manager,
                "borrowable_flag": borrowable,
                "borrowable_check": 1 if borrowable == "可借" else 0,
            }
        )
        return number

    def sheet(self, number: str = "SHEET-1", *, custodian: str = ME,
              status: str = "submitted", lines=None) -> int:
        requirement_sheet_service.create(
            {
                "sheet_number": number,
                "title": "蒸馏",
                "recipe_key": "distill",
                "status": status,
                "requester": TEACHER,
                "source_kind": "teaching",
                "source_code": "有机化学实验/蒸馏",
                "academic_year": "2026-2027",
                "custodian_scope": "person",
                "custodian_key": custodian,
            }
        )
        row = TEST_DB.execute_query(
            "SELECT id FROM requirement_sheet WHERE sheet_number = ?", (number,)
        )
        sheet_id = int(row[0]["id"])
        for seq, (substance, qty, unit) in enumerate(lines or [(ETHANOL, 80.0, "g")]):
            TEST_DB.execute_update(
                "INSERT INTO requirement_line (sheet_id, seq, substance_key, "
                "display_name, quantity, unit) VALUES (?, ?, ?, ?, ?, ?)",
                (sheet_id, seq, substance.key, substance.name, qty, unit),
            )
        return sheet_id

    # ---------------------------------------------------------------- 便利
    def _request(self, supplier: str = LI, sheet_number: str = "SHEET-1"):
        result = self.service.request(sheet_number, supplier, ME, note="测试")
        self.assertTrue(result.is_success(), result.message)
        return result.data["order"]

    @staticmethod
    def _manager_of(number: str) -> str:
        row = TEST_DB.execute_query(
            "SELECT manager FROM reagent_bottle WHERE bottle_number = ?", (number,)
        )
        return row[0]["manager"]


class TestTransferRules(unittest.TestCase):
    """纯判定（不碰库）"""

    def test_only_supplier_can_answer(self):
        self.assertTrue(can_answer(TRANSFER_REQUESTED, LI, LI))
        self.assertFalse(can_answer(TRANSFER_REQUESTED, LI, ME))
        self.assertFalse(can_answer(TRANSFER_ACCEPTED, LI, LI))

    def test_super_admin_can_answer_without_being_supplier(self):
        self.assertTrue(can_answer(TRANSFER_REQUESTED, LI, "超管", is_super_admin=True))

    def test_self_transfer_is_rejected(self):
        self.assertEqual(check_parties(LI, LI), ANSWER_SELF)
        self.assertIsNone(check_parties(LI, ME))

    def test_selections_split_all_partial_and_out_of_range(self):
        self.assertEqual(resolve_selections(3, None), ((0, 1, 2), ()))
        self.assertEqual(resolve_selections(3, [0, 2]), ((0, 2), (1,)))
        # 越界下标丢弃，不抛异常：页面下标可能是上一次渲染的
        self.assertEqual(resolve_selections(2, [0, 9]), ((0,), (1,)))
        self.assertEqual(resolve_selections(0, None), ((), ()))

    def test_reject_requires_reason(self):
        self.assertEqual(can_reject(TRANSFER_REQUESTED, ""), ANSWER_REMARK_REQUIRED)
        self.assertIsNone(can_reject(TRANSFER_REQUESTED, "我自己要用"))

    def test_cancel_only_for_requester_while_pending(self):
        self.assertTrue(can_cancel(TRANSFER_REQUESTED, ME, ME))
        self.assertFalse(can_cancel(TRANSFER_REQUESTED, ME, LI))
        self.assertFalse(can_cancel(TRANSFER_ACCEPTED, ME, ME))


class TestGapsAndProposal(_Base):
    def test_my_gaps_only_counts_claims_on_me(self):
        self.bottle("B-LI-1", 60.0, LI)
        self.sheet("SHEET-1", custodian=ME)
        self.sheet("SHEET-2", custodian=LI)          # 别人名下的单不算我的缺口
        self.sheet("SHEET-3", custodian="")          # 池子里的单没有主人

        gaps = self.service.my_gaps(ME)
        self.assertTrue(gaps.is_success(), gaps.message)
        numbers = [gap["sheet_number"] for gap in gaps.data]
        self.assertEqual(numbers, ["SHEET-1"])

    def test_proposal_groups_by_supplier(self):
        self.bottle("B-LI-1", 60.0, LI)
        self.bottle("B-ZHAO-1", 40.0, ZHAO)
        self.sheet("SHEET-1", lines=[(ETHANOL, 80.0, "g")])

        proposed = self.service.propose("SHEET-1", ME)
        self.assertTrue(proposed.is_success(), proposed.message)
        groups = proposed.data["groups"]
        self.assertEqual(sorted(group["supplier"] for group in groups), [LI, ZHAO])
        total = sum(line["quantity"] for group in groups for line in group["lines"])
        self.assertAlmostEqual(total, 80.0)
        self.assertEqual(proposed.data["unresolved"], [])

    def test_gap_shrinks_after_partial_issue(self):
        self.bottle("B-LI-1", 60.0, LI)
        self.bottle("B-ME-1", 30.0, ME)
        self.sheet("SHEET-1", lines=[(ETHANOL, 80.0, "g")])
        # 已兑付 30 g（自己名下那瓶）
        TEST_DB.execute_update(
            "UPDATE requirement_line SET issued_quantity = 30 WHERE sheet_id = "
            "(SELECT id FROM requirement_sheet WHERE sheet_number = 'SHEET-1')"
        )
        gap = self.service.gap_of("SHEET-1", ME)
        self.assertTrue(gap.is_success(), gap.message)
        self.assertAlmostEqual(gap.data["lines"][0]["remaining"], 50.0)


class TestRequestAndAnswer(_Base):
    def setUp(self):
        super().setUp()
        self.bottle("B-LI-1", 60.0, LI)
        self.bottle("B-ZHAO-1", 40.0, ZHAO)
        self.sheet("SHEET-1", lines=[(ETHANOL, 80.0, "g")])

    def test_request_creates_one_order_for_one_supplier(self):
        order = self._request(LI)
        self.assertEqual(order.from_manager, LI)
        self.assertEqual(order.to_manager, ME)
        self.assertEqual(order.status, TRANSFER_REQUESTED)
        self.assertEqual(len(order.items), 1)
        self.assertEqual(order.items[0].line_status, ITEM_PENDING)
        # 另一张单没被一起发出去：一人一单
        self.assertEqual(len(transfer_order_service.list_pending_for(ZHAO)), 0)

    def test_supplier_accept_moves_custody(self):
        order = self._request(LI)
        self.assertEqual(self._manager_of("B-LI-1"), LI)

        accepted = self.service.accept(order.id, LI, remark="给他")
        self.assertTrue(accepted.is_success(), accepted.message)
        self.assertEqual(self._manager_of("B-LI-1"), ME)
        self.assertEqual(transfer_order_service.get(order.id).status, TRANSFER_ACCEPTED)

        log = TEST_DB.execute_query(
            "SELECT ref_type, ref_id FROM manager_change_log WHERE bottle_number = ?",
            ("B-LI-1",),
        )
        self.assertEqual(log[-1]["ref_type"], "transfer_order")
        self.assertEqual(log[-1]["ref_id"], order.transfer_number)

    def test_beneficiary_cannot_answer(self):
        order = self._request(LI)
        refused = self.service.accept(order.id, ME)
        self.assertFalse(refused.is_success())
        self.assertEqual(self._manager_of("B-LI-1"), LI)
        self.assertEqual(transfer_order_service.get(order.id).status, TRANSFER_REQUESTED)

    def test_double_accept_is_blocked(self):
        order = self._request(LI)
        first = self.service.accept(order.id, LI)
        self.assertTrue(first.is_success(), first.message)
        second = self.service.accept(order.id, LI)
        self.assertFalse(second.is_success())
        # 第二次连门都进不了：状态已经不是「待点头」
        self.assertIn("不是「待点头」", second.message)
        self.assertEqual(transfer_order_service.get(order.id).status, TRANSFER_ACCEPTED)

    def test_reject_needs_reason_and_leaves_custody(self):
        order = self._request(LI)
        refused = self.service.reject(order.id, LI, "")
        self.assertFalse(refused.is_success())
        self.assertIn("理由", refused.message)

        rejected = self.service.reject(order.id, LI, "我这门课下周也要用")
        self.assertTrue(rejected.is_success(), rejected.message)
        self.assertEqual(transfer_order_service.get(order.id).status, TRANSFER_REJECTED)
        self.assertEqual(self._manager_of("B-LI-1"), LI)

    def test_cancel_by_requester_then_no_answer(self):
        order = self._request(LI)
        cancelled = self.service.cancel(order.id, ME)
        self.assertTrue(cancelled.is_success(), cancelled.message)
        late = self.service.accept(order.id, LI)
        self.assertFalse(late.is_success())

    def test_super_admin_signs_on_behalf_marks_forced(self):
        order = self._request(LI)
        signed = self.service.accept(
            order.id, "超管", remark="李四出差，代签", is_super_admin=True
        )
        self.assertTrue(signed.is_success(), signed.message)
        stored = transfer_order_service.get(order.id)
        self.assertEqual(stored.status, TRANSFER_ACCEPTED)
        self.assertEqual(stored.forced, 1)
        self.assertEqual(stored.respondent, "超管")
        self.assertEqual(self._manager_of("B-LI-1"), ME)


class TestPartialAndFailures(_Base):
    def test_partial_accept_only_moves_chosen_lines(self):
        self.bottle("B-LI-1", 30.0, LI)
        self.bottle("B-LI-2", 30.0, LI)
        self.sheet("SHEET-1", lines=[(ETHANOL, 60.0, "g")])
        order = self._request(LI)
        self.assertEqual(len(order.items), 2)

        accepted = self.service.accept(order.id, LI, selections=[0], remark="先给一瓶")
        self.assertTrue(accepted.is_success(), accepted.message)
        self.assertEqual(self._manager_of("B-LI-1"), ME)
        self.assertEqual(self._manager_of("B-LI-2"), LI)

        stored = transfer_order_service.get(order.id)
        self.assertEqual(stored.status, TRANSFER_ACCEPTED)
        self.assertEqual(stored.items[0].line_status, "已同意")
        self.assertEqual(stored.items[1].line_status, ITEM_DECLINED)

    def test_nothing_selected_is_refused(self):
        self.bottle("B-LI-1", 30.0, LI)
        self.sheet("SHEET-1", lines=[(ETHANOL, 30.0, "g")])
        order = self._request(LI)
        refused = self.service.accept(order.id, LI, selections=[])
        self.assertFalse(refused.is_success())
        self.assertEqual(refused.error_code, ANSWER_NO_SELECTION)

    def test_bottle_on_loan_rolls_the_whole_order_back(self):
        self.bottle("B-LI-1", 30.0, LI)
        self.sheet("SHEET-1", lines=[(ETHANOL, 30.0, "g")])
        order = self._request(LI)
        # 单发出去之后、点头之前，这瓶被借走了
        TEST_DB.execute_update(
            "UPDATE reagent_bottle SET borrowable_flag = '借用中', borrowable_check = 0 "
            "WHERE bottle_number = ?",
            ("B-LI-1",),
        )

        failed = self.service.accept(order.id, LI)
        self.assertFalse(failed.is_success())
        # 一瓶都没转成 → 单据不能停在「已同意」
        self.assertEqual(transfer_order_service.get(order.id).status, TRANSFER_REQUESTED)
        self.assertEqual(self._manager_of("B-LI-1"), LI)

    def test_multi_lot_line_is_split_per_bottle(self):
        self.bottle("B-LI-1", 20.0, LI)
        self.bottle("B-LI-2", 20.0, LI)
        self.sheet("SHEET-1", lines=[(ETHANOL, 40.0, "g")])
        # 建议里一行要动两瓶（"A,B"）：落单必须拆开，每瓶一行
        items = self.service._split_items(
            [
                {
                    "lot_id": "B-LI-1,B-LI-2",
                    "substance_key": ETHANOL.key,
                    "name": "乙醇",
                    "quantity": 40.0,
                    "unit": "g",
                }
            ]
        )
        self.assertEqual([item["lot_id"] for item in items], ["B-LI-1", "B-LI-2"])
        self.assertEqual([item["quantity"] for item in items], [20.0, 20.0])


if __name__ == "__main__":
    unittest.main()
