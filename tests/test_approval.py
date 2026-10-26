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
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from utils import audit as audit_module
from business.borrow_service import borrow_service
from business.purchase_service import purchase_service
from business.work_order_service import work_order_service
from services.base.controlled_list_service import controlled_list_service
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from services.core.borrow_order_service import (
    borrow_order_item_service,
    borrow_order_service,
)
from services.core.purchase_plan_service import (
    purchase_plan_item_service,
    purchase_plan_service,
)
from services.core.reagent_bottle_service import reagent_bottle_service

_TABLES = (
    "borrow_order_item", "borrow_order",
    "borrow_record", "return_record", "reagent_bottle",
    "experiment_item", "experiment_course",
    "controlled_list", "person", "operation_log",
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

    def _make_person(self, name: str, role: str = "teacher"):
        from services.base.person_service import person_service
        person_service.create({
            "name": name,
            "role": role,
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
        # 合格审批人须为人员表中的 admin 账号（正常提交排除超管）
        self._make_person(applicant, "teacher")
        if approver:
            self._make_person(approver, "admin")
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

    def test_controlled_without_cas_requires_approval(self):
        """无 CAS 但名称命中管控名录时，也必须进入审批而不是直接借出。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9006", "管控试剂", 100.0, cas="")
        self._make_person("李老师", "teacher")
        self._make_person("王管理员", "admin")

        created = work_order_service.create_order(
            order_type="课程领用",
            applicant="李老师",
            cart_items=[{
                "bottle_number": "B9006",
                "reagent_name": "管控试剂",
                "borrow_qty": 10.0,
            }],
            course=experiment_course_service.get_by_id(
                self._make_course(approver="王管理员")
            ),
            exp_item=experiment_item_service.get_by_id(self._make_item()),
        )
        self.assertTrue(created.is_success(), created.message)
        self.assertTrue(created.data.get("pending_approval"))
        self.assertAlmostEqual(
            float(reagent_bottle_service.get_by_bottle_number("B9006").remaining_quantity),
            100.0,
            msg="审批前不得扣库存",
        )

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

    def test_department_pool_order_approvable_by_colleague(self):
        """归教研室池的单，本室任一管理员都能批。

        这是「指定审批人休假」的正常出路：本人（或超管）把单退回教研室池，
        组里接手的人能直接批，签名落实际操作人，不留代签。
        """
        self._make_controlled("CN-111")
        self._make_bottle("B9201", "管控试剂", 100.0, cas="CN-111")
        created = self._create_controlled_course_order("B9201")
        order_id = created.data["order_id"]

        self._make_person("李管理员", "admin")
        TEST_DB.execute_update(
            "UPDATE person SET department = ? WHERE name IN (?, ?)",
            ("化学教研室", "王管理员", "李管理员"),
        )
        # 王管理员休假 → 单退回教研室池
        TEST_DB.execute_update(
            "UPDATE borrow_order SET custodian_scope = 'department', "
            "custodian_key = '化学教研室', claimed_at = NULL, "
            "claimed_from_scope = '', claimed_from_key = '' WHERE id = ?",
            (order_id,),
        )

        result = work_order_service.approve_order(order_id, "李管理员")
        self.assertTrue(result.is_success(), result.message)
        order = borrow_order_service.get_by_id(order_id)
        self.assertEqual(order.approver, "李管理员", "签名必须跟实际操作人走")

    def test_other_department_administrator_cannot_approve(self):
        """别的教研室的管理员批不了：收窄与放宽都只在本层成员内生效。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9202", "管控试剂", 100.0, cas="CN-111")
        created = self._create_controlled_course_order("B9202")
        order_id = created.data["order_id"]

        self._make_person("赵管理员", "admin")
        TEST_DB.execute_update(
            "UPDATE person SET department = ? WHERE name = ?",
            ("生物教研室", "赵管理员"),
        )
        TEST_DB.execute_update(
            "UPDATE borrow_order SET custodian_scope = 'department', "
            "custodian_key = '化学教研室' WHERE id = ?",
            (order_id,),
        )

        result = work_order_service.approve_order(order_id, "赵管理员")
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "NOT_ASSIGNED_APPROVER")

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

    def test_approve_partial_failure_marks_items_failed(self):
        """批准时个别瓶执行失败（如已被借走）→ 失败明细置终态「执行失败」。

        该瓶从未实际借出，若保留「待归还」状态会出现在待还列表，
        按流程归还将凭空虚增库存（QA 审查发现）。
        """
        self._make_controlled("CN-111")
        self._make_bottle("B9120", "管控试剂", 100.0, cas="CN-111")
        self._make_bottle("B9121", "管控试剂", 100.0, cas="CN-111")
        self._make_person("李老师", "teacher")
        self._make_person("王管理员", "admin")
        course_id = self._make_course(approver="王管理员")
        item_id = self._make_item()

        created = work_order_service.create_order(
            order_type="课程领用",
            applicant="李老师",
            cart_items=[
                {"bottle_number": "B9120", "reagent_name": "管控试剂",
                 "borrow_qty": 10.0},
                {"bottle_number": "B9121", "reagent_name": "管控试剂",
                 "borrow_qty": 10.0},
            ],
            course=experiment_course_service.get_by_id(course_id),
            exp_item=experiment_item_service.get_by_id(item_id),
        )
        self.assertTrue(created.is_success(), created.message)
        order_id = created.data["order_id"]

        ok = mock.Mock(is_success=mock.Mock(return_value=True),
                       data={"record_id": 9001})
        fail = mock.Mock(is_success=mock.Mock(return_value=False),
                         message="该试剂已被其他用户领用")
        with mock.patch.object(
            borrow_service, "reagent_borrow",
            side_effect=[ok, fail],
        ):
            result = work_order_service.approve_order(order_id, "王管理员")

        self.assertTrue(result.is_success(), result.message)
        statuses = {
            i.bottle_number: i.status
            for i in borrow_order_item_service.get_by_order(order_id)
        }
        self.assertEqual(statuses["B9120"], "待归还")
        self.assertEqual(statuses["B9121"], "执行失败")
        order = borrow_order_service.get_by_id(order_id)
        self.assertEqual(order.approval_status, "已批准")

    def test_update_where_stale_condition_and_race_guard(self):
        """条件更新 + 并发败卫（QA 审查发现 M6）。

        1. 条件不满足 → 不写入（原子抢占的基础）
        2. 已撤回工单再「批准」→ 拒绝，且不扣库存
        """
        self._make_controlled("CN-111")
        self._make_bottle("B9130", "管控试剂", 100.0, cas="CN-111")
        created = self._create_controlled_course_order("B9130")
        order_id = created.data["order_id"]

        # 条件为「已批准」（实际是待审批）→ 未命中，不发生写入
        self.assertFalse(borrow_order_service.update_where(
            {"id": order_id, "approval_status": "已批准"},
            {"status": "借用中"},
        ))
        order = borrow_order_service.get_by_id(order_id)
        self.assertEqual(order.approval_status, "待审批")
        self.assertEqual(order.status, "待审批")

        # 申请人撤回后，审批人再批准：必须失败且库存不变
        withdraw = work_order_service.withdraw_order(order_id, "李老师")
        self.assertTrue(withdraw.is_success(), withdraw.message)
        result = work_order_service.approve_order(order_id, "王管理员")
        self.assertTrue(result.is_failure())

        bottle = reagent_bottle_service.get_by_bottle_number("B9130")
        self.assertAlmostEqual(float(bottle.remaining_quantity), 100.0)

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

    # ---------------- 审批人边界（决策 1）----------------
    def test_sporadic_no_longer_auto_picks_super_admin(self):
        """零星领用不再自动取第一个超管：未指定审批人 → NO_APPROVER。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9101", "管控试剂", 100.0, cas="CN-111")

        result = work_order_service.create_order(
            order_type="零星领用",
            applicant="张三",
            cart_items=[{"bottle_number": "B9101", "reagent_name": "管控试剂",
                         "borrow_qty": 10.0}],
        )
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "NO_APPROVER")

    def test_sporadic_manual_approver_persisted(self):
        """零星领用手动指定管理员审批人并落库。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9102", "管控试剂", 100.0, cas="CN-111")
        self._make_person("张三", "teacher")
        self._make_person("王管理员", "admin")

        result = work_order_service.create_order(
            order_type="零星领用",
            applicant="张三",
            cart_items=[{"bottle_number": "B9102", "reagent_name": "管控试剂",
                         "borrow_qty": 10.0}],
            approver_name="王管理员",
        )
        self.assertTrue(result.is_success(), result.message)
        order = borrow_order_service.get_by_id(result.data["order_id"])
        self.assertEqual(order.approver, "王管理员")

    def test_super_admin_as_approver_rejected(self):
        """正常提交传超管审批 → 拒绝（超管接管只走应急改派）。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9103", "管控试剂", 100.0, cas="CN-111")
        self._make_person("张三", "teacher")
        self._make_person("超管甲", "super_admin")

        result = work_order_service.create_order(
            order_type="零星领用",
            applicant="张三",
            cart_items=[{"bottle_number": "B9103", "reagent_name": "管控试剂",
                         "borrow_qty": 10.0}],
            approver_name="超管甲",
        )
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "SUPER_ADMIN_APPROVER")

    def test_non_admin_approver_rejected(self):
        """审批人不是管理员账号（含不在人员表中的名字）→ 拒绝。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9104", "管控试剂", 100.0, cas="CN-111")
        self._make_person("张三", "teacher")

        result = work_order_service.create_order(
            order_type="零星领用",
            applicant="张三",
            cart_items=[{"bottle_number": "B9104", "reagent_name": "管控试剂",
                         "borrow_qty": 10.0}],
            approver_name="查无此人",
        )
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "INVALID_APPROVER_ROLE")

    def test_self_approval_still_rejected(self):
        """自审批（审批人 == 申请人）维持拒绝。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9105", "管控试剂", 100.0, cas="CN-111")
        self._make_person("李老师", "teacher")
        self._make_person("王管理员", "admin")

        result = work_order_service.create_order(
            order_type="零星领用",
            applicant="李老师",
            cart_items=[{"bottle_number": "B9105", "reagent_name": "管控试剂",
                         "borrow_qty": 10.0}],
            approver_name="李老师",
        )
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "SELF_APPROVAL")

    # ---------------- 撤回 ----------------
    def test_withdraw_by_applicant(self):
        """申请人本人可撤回 PENDING 工单：状态置「已撤回」。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9106", "管控试剂", 100.0, cas="CN-111")
        created = self._create_controlled_course_order("B9106")
        order_id = created.data["order_id"]

        result = work_order_service.withdraw_order(order_id, "李老师")
        self.assertTrue(result.is_success(), result.message)
        order = borrow_order_service.get_by_id(order_id)
        self.assertEqual(order.status, "已撤回")
        self.assertEqual(order.approval_status, "已撤回")
        # 库存不变
        bottle = reagent_bottle_service.get_by_bottle_number("B9106")
        self.assertAlmostEqual(float(bottle.remaining_quantity), 100.0)

    def test_withdraw_permission(self):
        """撤回权限：申请人本人或 admin+ 可撤回，其他人拒绝。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9107", "管控试剂", 100.0, cas="CN-111")
        created = self._create_controlled_course_order("B9107")
        order_id = created.data["order_id"]

        # 无关人员拒绝
        bad = work_order_service.withdraw_order(order_id, "路人甲")
        self.assertTrue(bad.is_failure())
        self.assertEqual(bad.error_code, "WITHDRAW_FORBIDDEN")

        # 管理员可代撤
        self._make_person("赵管理员", "admin")
        ok = work_order_service.withdraw_order(order_id, "赵管理员")
        self.assertTrue(ok.is_success(), ok.message)

        # 已撤回后不可再撤
        again = work_order_service.withdraw_order(order_id, "李老师")
        self.assertTrue(again.is_failure())
        self.assertEqual(again.error_code, "INVALID_APPROVAL_STATE")

    # ---------------- 应急重新指定审批人 ----------------
    def test_reassign_by_admin_updates_approver_and_audit(self):
        """管理员应急改派：审批人更新、审计标记「应急重新指定审批人」。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9108", "管控试剂", 100.0, cas="CN-111")
        created = self._create_controlled_course_order("B9108")
        order_id = created.data["order_id"]
        self._make_person("超管甲", "super_admin")

        # 审计标记（审计日志已四库分离，这里 mock utils.audit 断言调用参数）
        with mock.patch.object(audit_module, "audit") as _audit_mock:
            result = work_order_service.reassign_approver(
                order_id, "超管甲", "王管理员"
            )
        self.assertTrue(result.is_success(), result.message)
        _audit_mock.assert_called_once()
        _args, _kwargs = _audit_mock.call_args
        self.assertEqual(_args[0], "王管理员")
        self.assertEqual(_args[1], "应急重新指定审批人")
        self.assertIn("应急重新指定审批人", _kwargs.get("detail") or "")

        order = borrow_order_service.get_by_id(order_id)
        self.assertEqual(order.approver, "超管甲")

        # 改派后由新审批人审批
        approved = work_order_service.approve_order(order_id, "超管甲")
        self.assertTrue(approved.is_success(), approved.message)

    def test_reassign_permission_and_self_check(self):
        """应急改派权限：仅 admin+；新审批人不能是申请人。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9109", "管控试剂", 100.0, cas="CN-111")
        created = self._create_controlled_course_order("B9109")
        order_id = created.data["order_id"]

        # 非管理员拒绝
        bad = work_order_service.reassign_approver(order_id, "王管理员", "路人甲")
        self.assertTrue(bad.is_failure())
        self.assertEqual(bad.error_code, "REASSIGN_FORBIDDEN")

        # 新审批人是申请人本人 → 拒绝
        bad2 = work_order_service.reassign_approver(order_id, "李老师", "王管理员")
        self.assertTrue(bad2.is_failure())
        self.assertEqual(bad2.error_code, "SELF_APPROVAL")

        # 非管理员/超管账号 → 拒绝
        bad3 = work_order_service.reassign_approver(order_id, "查无此人", "王管理员")
        self.assertTrue(bad3.is_failure())
        self.assertEqual(bad3.error_code, "INVALID_APPROVER_ROLE")

    # ---------------- 审计操作人（T10）----------------
    def test_audit_operator_is_created_by(self):
        """代发起时审计记录实际操作人 created_by，并注明「代 xx 提交」。"""
        self._make_controlled("CN-111")
        self._make_bottle("B9110", "管控试剂", 100.0, cas="CN-111")
        self._make_person("李老师", "teacher")
        self._make_person("王管理员", "admin")
        self._make_person("钱管理员", "admin")

        # 审计日志已四库分离，这里 mock utils.audit 断言提交审批的审计参数
        with mock.patch.object(audit_module, "audit") as _audit_mock:
            created = work_order_service.create_order(
                order_type="课程领用",
                applicant="李老师",
                cart_items=[{"bottle_number": "B9110", "reagent_name": "管控试剂",
                             "borrow_qty": 10.0}],
                course=experiment_course_service.get_by_id(
                    self._make_course(approver="王管理员")
                ),
                exp_item=experiment_item_service.get_by_id(self._make_item()),
                created_by="钱管理员",
            )
        self.assertTrue(created.is_success(), created.message)

        _audit_mock.assert_called_once()
        _args, _kwargs = _audit_mock.call_args
        self.assertEqual(_args[0], "钱管理员", "审计应记录实际操作人 created_by")
        self.assertEqual(_args[1], "提交审批")
        self.assertIn("代 李老师 提交", _kwargs.get("detail") or "")


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
