"""审批流程测试（隔离临时库）

覆盖：
- 普通试剂工单：无需审批，直接扣库存
- 含管控试剂的课程领用：待审批、不扣库存 → 批准后自动领用
- 驳回：工单关闭、库存不变
- 审批权限：仅课程绑定的审批管理员可审批
- 课程未绑定审批管理员 / 审批人即发起人 → 明确拒绝
- 采购审批：含管控 → 提交审批 → 批准 / 驳回 / 禁止自审自批
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.purchase_service import purchase_service
from business.work_order_service import work_order_service
from services.base.controlled_list_service import controlled_list_service
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from services.core.borrow_order_service import borrow_order_service
from services.core.purchase_plan_service import (
    purchase_plan_item_service,
    purchase_plan_service,
)
from services.core.reagent_bottle_service import reagent_bottle_service

_TABLES = (
    "borrow_order_item", "borrow_order",
    "borrow_record", "return_record", "reagent_bottle",
    "experiment_item", "experiment_course",
    "controlled_list", "person",
    "purchase_plan_item", "purchase_plan",
)


class TestBorrowApproval(unittest.TestCase):
    def setUp(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    def tearDown(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    # ---------------- 辅助 ----------------
    def _make_controlled(self, cas: str):
        controlled_list_service.create({
            "chemical_name": "管控试剂",
            "cas_number": cas,
            "dangerous_type": "易制毒",
        })

    def _make_bottle(self, bottle_number, reagent_name, remaining, cas="CN-000"):
        reagent_bottle_service.create({
            "bottle_number": bottle_number,
            "reagent_name": reagent_name,
            "cas_number": cas,
            "remaining_quantity": remaining,
            "borrowable_flag": "可借",
            "expired_flag": "正常",
        })

    def _make_course(self, approver=None, students=20):
        return experiment_course_service.create({
            "semester": "2026-2027", "term": "1",
            "course_name": "测试课程", "class_name": "1班",
            "major": "食安", "teacher": "测试老师",
            "student_count": students, "approver": approver,
        })

    def _make_item(self, course_name="测试课程", item_name="实验一"):
        return experiment_item_service.create({
            "semester": "2026-2027", "course_name": course_name,
            "seq": 1, "item_name": item_name,
        })

    def _create_controlled_course_order(self, bottle_number, applicant="李老师",
                                        approver="王管理员"):
        course_id = self._make_course(approver=approver)
        item_id = self._make_item()
        created = work_order_service.create_order(
            order_type="课程领用",
            applicant=applicant,
            cart_items=[{
                "bottle_number": bottle_number,
                "reagent_name": "管控试剂",
                "borrow_qty": 10.0,
            }],
            course=experiment_course_service.get_by_id(course_id),
            exp_item=experiment_item_service.get_by_id(item_id),
        )
        return created

    # ---------------- 普通试剂 ----------------
    def test_normal_reagent_skips_approval(self):
        """不含管控试剂的工单：无需审批，立即扣库存。"""
        self._make_bottle("B9001", "试剂甲", 100.0)
        result = work_order_service.create_order(
            order_type="零星领用",
            applicant="张三",
            cart_items=[{"bottle_number": "B9001", "reagent_name": "试剂甲", "borrow_qty": 10.0}],
        )
        self.assertTrue(result.is_success(), result.message)
        self.assertFalse(result.data.get("pending_approval"))

        order = borrow_order_service.get_by_id(result.data["order_id"])
        self.assertEqual(order.approval_status, "无需审批")
        self.assertEqual(order.status, "借用中")

        bottle = reagent_bottle_service.get_by_bottle_number("B9001")
        self.assertAlmostEqual(float(bottle.remaining_quantity), 90.0)

    # ---------------- 管控试剂 ----------------
    def test_controlled_order_requires_approval(self):
        """含管控试剂：工单待审批、不扣库存，审批人为课程绑定管理员。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9002", "管控试剂", 100.0, cas="CN-111")

        created = self._create_controlled_course_order("B9002")
        self.assertTrue(created.is_success(), created.message)
        self.assertTrue(created.data["pending_approval"])
        self.assertEqual(created.data["approver"], "王管理员")

        order = borrow_order_service.get_by_id(created.data["order_id"])
        self.assertEqual(order.status, "待审批")
        self.assertEqual(order.approval_status, "待审批")
        self.assertEqual(order.approver, "王管理员")

        # 库存不变（批准前不扣）
        bottle = reagent_bottle_service.get_by_bottle_number("B9002")
        self.assertAlmostEqual(float(bottle.remaining_quantity), 100.0)

    def test_course_without_approver_rejected(self):
        """课程未绑定审批管理员时应明确拒绝（NO_APPROVER）。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9003", "管控试剂", 100.0, cas="CN-111")

        result = self._create_controlled_course_order("B9003", approver=None)
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "NO_APPROVER")

    def test_only_assigned_approver_can_approve(self):
        """非指定审批人不能批准。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9004", "管控试剂", 100.0, cas="CN-111")

        created = self._create_controlled_course_order("B9004")
        order_id = created.data["order_id"]

        result = work_order_service.approve_order(order_id, "路人甲")
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "NOT_ASSIGNED_APPROVER")

        order = borrow_order_service.get_by_id(order_id)
        self.assertEqual(order.approval_status, "待审批")

    def test_approve_executes_borrow(self):
        """批准后自动执行领用：扣库存、工单借用中、待办清空。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9005", "管控试剂", 100.0, cas="CN-111")

        created = self._create_controlled_course_order("B9005")
        order_id = created.data["order_id"]

        result = work_order_service.approve_order(order_id, "王管理员", "同意")
        self.assertTrue(result.is_success(), result.message)

        order = borrow_order_service.get_by_id(order_id)
        self.assertEqual(order.status, "借用中")
        self.assertEqual(order.approval_status, "已批准")

        bottle = reagent_bottle_service.get_by_bottle_number("B9005")
        self.assertAlmostEqual(float(bottle.remaining_quantity), 90.0)

        self.assertEqual(work_order_service.list_pending_approvals("王管理员"), [])

    def test_reject_closes_order(self):
        """驳回：工单关闭、库存不变。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9006", "管控试剂", 100.0, cas="CN-111")

        created = self._create_controlled_course_order("B9006")
        order_id = created.data["order_id"]

        result = work_order_service.reject_order(order_id, "王管理员", "数量不合理")
        self.assertTrue(result.is_success(), result.message)

        order = borrow_order_service.get_by_id(order_id)
        self.assertEqual(order.status, "已驳回")
        self.assertEqual(order.approval_status, "已驳回")

        bottle = reagent_bottle_service.get_by_bottle_number("B9006")
        self.assertAlmostEqual(float(bottle.remaining_quantity), 100.0)


class TestPurchaseApproval(unittest.TestCase):
    def setUp(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()
        self._make_controlled("CN-222")

    def tearDown(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    def _make_controlled(self, cas: str):
        controlled_list_service.create({
            "chemical_name": "管控试剂B",
            "cas_number": cas,
            "dangerous_type": "易制爆",
        })

    def _make_plan(self):
        plan_id = purchase_plan_service.create({
            "plan_number": "CP001",
            "course_name": "采购课程",
            "source_semester": "2025-2026",
            "target_semester": "2026-2027",
            "status": "待采购",
            "approval_status": "无需审批",
            "created_by": "钱管理员",
        })
        purchase_plan_item_service.create({
            "plan_id": plan_id,
            "reagent_name": "管控试剂B",
            "cas_number": "CN-222",
            "demand_quantity": 50.0,
            "purchase_quantity": 50.0,
        })
        return plan_id

    def test_purchase_submit_and_approve(self):
        """含管控的采购单：提交审批 → 指定审批人批准。"""
        plan_id = self._make_plan()

        result = purchase_service.submit_for_approval(plan_id, "赵管理员", "钱管理员")
        self.assertTrue(result.is_success(), result.message)

        plan = purchase_plan_service.get_by_id(plan_id)
        self.assertEqual(plan.approval_status, "待审批")
        self.assertEqual(plan.approver, "赵管理员")

        bad = purchase_service.approve_purchase(plan_id, "路人甲")
        self.assertTrue(bad.is_failure())

        ok = purchase_service.approve_purchase(plan_id, "赵管理员", "同意")
        self.assertTrue(ok.is_success(), ok.message)
        self.assertEqual(
            purchase_plan_service.get_by_id(plan_id).approval_status, "已批准"
        )

    def test_purchase_reject(self):
        """采购单驳回。"""
        plan_id = self._make_plan()
        purchase_service.submit_for_approval(plan_id, "赵管理员", "钱管理员")

        result = purchase_service.reject_purchase(plan_id, "赵管理员", "预算不足")
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(
            purchase_plan_service.get_by_id(plan_id).approval_status, "已驳回"
        )

    def test_purchase_self_approval_rejected(self):
        """采购审批禁止自审自批。"""
        plan_id = self._make_plan()
        result = purchase_service.submit_for_approval(plan_id, "钱管理员", "钱管理员")
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "INVALID_APPROVER")


if __name__ == "__main__":
    unittest.main()
