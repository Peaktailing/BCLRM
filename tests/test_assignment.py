"""归属三级降级：谁能看、谁能接、谁能退。

这一组用例守的是一条容易被写散的不变量：

    **同教研室的其他管理员没有退回权。**

认领是单向收窄（组 → 人）。如果同室旁人能把归属改回去，认领就退化成
一个可被第三方撤回的临时状态，抢单只是从「接单」挪到了「退回」按钮上。
所以「可见」与「可改」必须是两条规则，不能共用一条。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB

from business.assignment_service import (
    KIND_ORDER,
    KIND_REQUIREMENT,
    AssignmentService,
)
from domain.assignment import (
    CLAIM_ASSIGNED,
    CLAIM_OTHER_DEPARTMENT,
    CLAIM_TAKEN,
    RELEASE_NOT_OWNER,
    Assignment,
    assignment_of,
)
from domain.custody import Custodian

PREFIX = "ASG-T-"


class _Person:
    def __init__(self, name: str, department: str = "", role: str = "admin") -> None:
        self.name = name
        self.department = department
        self.role = role


class _People:
    """最小人员目录：科室与角色现查，与真实 person_service 同形。"""

    def __init__(self, persons) -> None:
        self._by_name = {p.name: p for p in persons}

    def get_by_name(self, name):
        return self._by_name.get(name)

    def get_all_persons(self):
        return list(self._by_name.values())


class _Routes:
    def __init__(self, rules=None) -> None:
        self._rules = rules or {}

    def rules(self, scope_type, department_of=None):
        return self._rules.get(scope_type, {})


PEOPLE = _People(
    [
        _Person("张三", "化学教研室"),
        _Person("李四", "化学教研室"),     # 与张三同室
        _Person("王五", "生物教研室"),
        _Person("赵六", "化学教研室", role="teacher"),
        _Person("超管", "化学教研室", role="super_admin"),
    ]
)


def _service(rules=None) -> AssignmentService:
    return AssignmentService(database=TEST_DB, routes=_Routes(rules), people=PEOPLE)


class TestAssignmentRules(unittest.TestCase):
    """纯领域判定，不碰库。"""

    def test_blank_scope_falls_back_to_all(self):
        self.assertTrue(Assignment.of("", "").is_all)
        self.assertTrue(Assignment.of("person", "").is_all)   # 人名丢了，退 all
        self.assertTrue(Assignment.of("weird", "x").is_all)

    def test_person_visible_only_to_self(self):
        target = Assignment.person("张三")
        self.assertTrue(target.visible_to("张三", "化学教研室"))
        self.assertFalse(target.visible_to("李四", "化学教研室"))

    def test_department_visible_to_same_department_only(self):
        target = Assignment.department("化学教研室")
        self.assertTrue(target.visible_to("张三", "化学教研室"))
        self.assertFalse(target.visible_to("王五", "生物教研室"))
        # 没登记科室的人不该靠空值命中「空教研室」
        self.assertFalse(target.visible_to("无科室", ""))

    def test_person_cannot_be_claimed_even_by_owner(self):
        target = Assignment.person("张三")
        self.assertFalse(target.can_claim("张三", "化学教研室"))
        self.assertFalse(target.can_claim("超管", "化学教研室", is_super_admin=True))

    def test_department_claim_requires_same_department(self):
        target = Assignment.department("化学教研室")
        self.assertTrue(target.can_claim("张三", "化学教研室"))
        self.assertFalse(target.can_claim("王五", "生物教研室"))
        self.assertTrue(target.can_claim("超管", "生物教研室", is_super_admin=True))

    def test_same_department_administrator_cannot_release(self):
        """本轮的定盘星：组内可见 ≠ 组内可改。"""
        target = Assignment.person("张三")
        self.assertTrue(target.can_release("张三"))
        self.assertFalse(target.can_release("李四", is_super_admin=False))
        self.assertFalse(target.can_transfer("李四"))
        self.assertTrue(target.can_release("超管", is_super_admin=True))

    def test_department_row_can_only_be_released_by_super(self):
        target = Assignment.department("化学教研室")
        self.assertFalse(target.can_release("张三"))
        self.assertTrue(target.can_release("超管", is_super_admin=True))

    def test_root_pool_has_no_release(self):
        self.assertFalse(Assignment.everywhere().can_release("张三", is_super_admin=True))
        self.assertIsNone(Assignment.everywhere().after_release("化学教研室"))

    def test_release_restores_claimed_from(self):
        """认领来的单退回原处：原来在全院池就回全院池，不能被降成「他的教研室」。"""
        provider = Assignment.everywhere()
        self.assertTrue(Assignment.person("张三").after_release("化学教研室", provider).is_all)

        from_department = Assignment.department("生物教研室")
        restored = Assignment.person("张三").after_release("化学教研室", from_department)
        self.assertEqual(restored.scope, "department")
        self.assertEqual(restored.key, "生物教研室")

    def test_release_demotes_assigned_order(self):
        """指定来的单（没有 claimed_from）降一级。"""
        target = Assignment.person("张三")
        demoted = target.after_release("化学教研室", None)
        self.assertEqual(demoted.scope, "department")
        self.assertEqual(demoted.key, "化学教研室")
        # 没有教研室的人，退回只能落到全院
        self.assertTrue(target.after_release("", None).is_all)

    def test_assignment_of_reads_legacy_blank_as_all(self):
        self.assertTrue(assignment_of({"custodian_scope": "", "custodian_key": ""}).is_all)
        self.assertTrue(assignment_of({}).is_all)


class TestAssignmentService(unittest.TestCase):
    """服务层：能看、能接、能退，落到库上的结果。"""

    def setUp(self):
        # 只清本用例前缀的行：测试库与其他用例共享，清表会误伤。
        TEST_DB.connection.execute(
            "DELETE FROM borrow_order WHERE order_number LIKE ?", (PREFIX + "%",)
        )
        TEST_DB.connection.execute(
            "DELETE FROM requirement_sheet WHERE sheet_number LIKE ?", (PREFIX + "%",)
        )
        TEST_DB.connection.commit()
        self.service = _service()

    def _order(self, suffix: str, applicant="赵六", scope="", key="",
               status="待审批", approval="待审批"):
        number = f"{PREFIX}{suffix}"
        TEST_DB.execute_insert(
            "INSERT INTO borrow_order (order_number, order_type, applicant, status, "
            "approval_status, custodian_scope, custodian_key) VALUES (?,?,?,?,?,?,?)",
            (number, "零星领用", applicant, status, approval, scope, key),
        )
        return number

    # ---------------------------------------------------------------- 队列
    def test_queue_three_or_filters(self):
        mine = self._order("q1", scope="person", key="张三")
        room = self._order("q2", scope="department", key="化学教研室")
        pool = self._order("q3", scope="all", key="")
        other = self._order("q4", scope="department", key="生物教研室")

        refs = [r["ref"] for r in self.service.queue("张三", "化学教研室")]
        self.assertIn(mine, refs)
        self.assertIn(room, refs)
        self.assertIn(pool, refs)
        self.assertNotIn(other, refs)

    def test_legacy_blank_assignment_stays_visible(self):
        """老数据两列为空 → 按 all 处理。写成 `= 'all'` 会让历史单凭空消失。"""
        legacy = self._order("legacy", scope="", key="")
        refs = [r["ref"] for r in self.service.queue("张三", "化学教研室")]
        self.assertIn(legacy, refs)

    def test_finished_order_leaves_queue(self):
        done = self._order("done", scope="all", key="", status="借用中", approval="无需审批")
        refs = [r["ref"] for r in self.service.queue("张三", "化学教研室")]
        self.assertNotIn(done, refs)

    def test_requirement_sheet_in_same_queue(self):
        number = f"{PREFIX}req1"
        TEST_DB.execute_insert(
            "INSERT INTO requirement_sheet (sheet_number, title, requester, status, "
            "custodian_scope, custodian_key) VALUES (?,?,?,?,?,?)",
            (number, "有机合成", "赵六", "submitted", "all", ""),
        )
        rows = self.service.queue("张三", "化学教研室", kinds=(KIND_REQUIREMENT,))
        self.assertIn(number, [r["ref"] for r in rows])

    # ---------------------------------------------------------------- 认领
    def test_claim_writes_owner_and_records_from(self):
        number = self._order("c1", scope="all", key="")
        result = self.service.claim(KIND_ORDER, number, "张三", "化学教研室")
        self.assertTrue(result.is_success(), result.message)

        row = TEST_DB.execute_query(
            "SELECT * FROM borrow_order WHERE order_number = ?", (number,)
        )[0]
        self.assertEqual(row["custodian_scope"], "person")
        self.assertEqual(row["custodian_key"], "张三")
        self.assertEqual(row["claimed_from_scope"], "all")
        self.assertTrue(row["claimed_at"])

    def test_claim_taken_reports_who(self):
        number = self._order("c2", scope="all", key="")
        self.service.claim(KIND_ORDER, number, "张三", "化学教研室")
        again = self.service.claim(KIND_ORDER, number, "李四", "化学教研室")
        self.assertFalse(again.is_success())
        self.assertEqual(again.error_code, CLAIM_TAKEN.upper())
        self.assertIn("张三", again.message)

    def test_claim_other_department_rejected(self):
        number = self._order("c3", scope="department", key="生物教研室")
        result = self.service.claim(KIND_ORDER, number, "张三", "化学教研室")
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, CLAIM_OTHER_DEPARTMENT.upper())

    def test_claim_assigned_order_rejected(self):
        number = self._order("c4", scope="person", key="王五")
        result = self.service.claim(KIND_ORDER, number, "张三", "化学教研室")
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, CLAIM_ASSIGNED.upper())
        self.assertIn("王五", result.message)

    # ---------------------------------------------------------------- 退回
    def test_same_department_administrator_cannot_release(self):
        """李四与张三同室，也看得到这张单，但不能退。"""
        number = self._order("r1", scope="person", key="张三")
        result = self.service.release(KIND_ORDER, number, "李四", "化学教研室")
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, RELEASE_NOT_OWNER.upper())
        row = TEST_DB.execute_query(
            "SELECT custodian_key FROM borrow_order WHERE order_number = ?", (number,)
        )[0]
        self.assertEqual(row["custodian_key"], "张三")

    def test_owner_release_returns_to_original_pool(self):
        """认领来的单，退回回到原来那一级（all），不降成「他的教研室」。"""
        number = self._order("r2", scope="all", key="")
        self.service.claim(KIND_ORDER, number, "张三", "化学教研室")
        result = self.service.release(KIND_ORDER, number, "张三", "化学教研室")
        self.assertTrue(result.is_success(), result.message)
        row = TEST_DB.execute_query(
            "SELECT * FROM borrow_order WHERE order_number = ?", (number,)
        )[0]
        self.assertEqual(row["custodian_scope"], "all")
        self.assertEqual(row["custodian_key"], "")
        self.assertFalse(row["claimed_at"])
        self.assertEqual(row["claimed_from_scope"], "")

    def test_assigned_order_release_demotes_to_department(self):
        number = self._order("r3", scope="person", key="张三")
        result = self.service.release(KIND_ORDER, number, "张三", "化学教研室")
        self.assertTrue(result.is_success(), result.message)
        row = TEST_DB.execute_query(
            "SELECT custodian_scope, custodian_key FROM borrow_order WHERE order_number = ?",
            (number,),
        )[0]
        self.assertEqual(row["custodian_scope"], "department")
        self.assertEqual(row["custodian_key"], "化学教研室")

    def test_super_admin_can_release_other_people(self):
        number = self._order("r4", scope="person", key="张三")
        result = self.service.release(KIND_ORDER, number, "超管", "化学教研室")
        self.assertTrue(result.is_success(), result.message)

    # ---------------------------------------------------------------- 转交
    def test_transfer_requires_admin_target(self):
        number = self._order("t1", scope="person", key="张三")
        bad = self.service.transfer(KIND_ORDER, number, "赵六", "张三")
        self.assertFalse(bad.is_success())
        ok = self.service.transfer(KIND_ORDER, number, "李四", "张三")
        self.assertTrue(ok.is_success(), ok.message)

    # ---------------------------------------------------------------- 算归属
    def test_resolve_target_three_levels(self):
        rules = {"course": {"有机化学": Custodian("张三", "化学教研室")}}
        service = _service(rules)
        self.assertEqual(service.resolve_target("赵六", "有机化学").key, "张三")
        # 有班级时退到课程名
        self.assertEqual(service.resolve_target("赵六", "有机化学/1班").key, "张三")
        # 没课程规则 → 申请人教研室
        self.assertEqual(service.resolve_target("赵六", "无机化学").scope, "department")
        # 连教研室都没有 → 全院池
        self.assertTrue(service.resolve_target("无名氏", "").is_all)


if __name__ == "__main__":
    unittest.main()
