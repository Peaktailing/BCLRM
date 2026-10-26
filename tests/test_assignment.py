"""归属三级降级：谁能看、谁能接、谁能办、谁能退。

这一组用例守的是同一条总纲：

    **权限由「当前归属」决定，不由历史决定。**

收窄到人，别人当场看不见也动不了；放宽回组，组里每个人当场看得见、退得
动、批得动。两个方向互为镜像，所以用例也成对写。
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
    RETURN_NOT_MEMBER,
    RETURN_NOT_REQUESTER,
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
        # 超管的科室故意与化学教研室不同：用它验证「代退落到原持有人的
        # 教研室，而不是操作人的教研室」。
        _Person("超管", "生物教研室", role="super_admin"),
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

    def test_return_right_follows_membership(self):
        """能办的人才能退：收窄到人只有本人，组池本室任一，全院池任一。"""
        person = Assignment.person("张三")
        self.assertTrue(person.can_return("张三", "化学教研室", is_admin=True))
        self.assertFalse(person.can_return("李四", "化学教研室", is_admin=True))
        self.assertFalse(person.visible_to("李四", "化学教研室"))
        self.assertFalse(person.can_transfer("李四"))
        self.assertTrue(person.can_return("超管", "生物教研室", is_super_admin=True))

        room = Assignment.department("化学教研室")
        self.assertTrue(room.can_return("李四", "化学教研室", is_admin=True))
        self.assertFalse(room.can_return("赵六", "化学教研室", is_admin=False))  # 教师
        self.assertFalse(room.can_return("王五", "生物教研室", is_admin=True))

        pool = Assignment.everywhere()
        self.assertTrue(pool.can_return("王五", "生物教研室", is_admin=True))
        self.assertFalse(pool.can_return("赵六", "化学教研室", is_admin=False))

    def test_handle_follows_scope(self):
        """「能办」跟「能看」同一套成员集合；person 层超管也不代办。"""
        person = Assignment.person("张三")
        self.assertTrue(person.can_handle("张三", "化学教研室", is_admin=True))
        self.assertFalse(person.can_handle("李四", "化学教研室", is_admin=True))
        self.assertFalse(person.can_handle("超管", "生物教研室", is_super_admin=True))

        room = Assignment.department("化学教研室")
        self.assertTrue(room.can_handle("李四", "化学教研室", is_admin=True))
        self.assertFalse(room.can_handle("赵六", "化学教研室", is_admin=False))  # 教师
        self.assertFalse(room.can_handle("王五", "生物教研室", is_admin=True))
        self.assertFalse(room.can_handle("超管", "生物教研室", is_super_admin=True))

        pool = Assignment.everywhere()
        self.assertTrue(pool.can_handle("王五", "生物教研室", is_admin=True))
        self.assertFalse(pool.can_handle("赵六", "化学教研室", is_admin=False))

    def test_return_always_lands_on_requester(self):
        """不管原来在哪一层，退回落点都是申请人——不是上一级池。"""
        for target in (
            Assignment.person("张三"),
            Assignment.department("化学教研室"),
            Assignment.everywhere(),
        ):
            landed = target.returned_to("赵六")
            self.assertTrue(landed.is_person)
            self.assertEqual(landed.key, "赵六")
        # 没有申请人时兜底到全院池，不造出 person:""
        self.assertTrue(Assignment.person("张三").returned_to("").is_all)

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

    # ------------------------------------------------------------ 退回修改
    def test_return_without_reason_is_allowed(self):
        """原因不是必填：退这个动作本身已经说明「不能按现在这样批」。"""
        number = self._order("r1", scope="person", key="张三", applicant="赵六")
        result = self.service.return_for_revision(KIND_ORDER, number, "张三", "   ")
        self.assertTrue(result.is_success(), result.message)
        row = TEST_DB.execute_query(
            "SELECT approval_status, approval_remark, custodian_key "
            "FROM borrow_order WHERE order_number = ?",
            (number,),
        )[0]
        self.assertEqual(row["approval_status"], "已驳回")
        self.assertEqual(row["custodian_key"], "赵六")
        self.assertIn(row["approval_remark"] or "", ("", None))

    def test_return_sends_order_back_to_requester(self):
        """退回落点是申请人，不是池；顺带关闭工单、写进退回原因。"""
        number = self._order("r2", scope="person", key="张三", applicant="赵六")
        result = self.service.return_for_revision(
            KIND_ORDER, number, "张三", "第 2 行数量按人数算多了", "化学教研室"
        )
        self.assertTrue(result.is_success(), result.message)

        row = TEST_DB.execute_query(
            "SELECT * FROM borrow_order WHERE order_number = ?", (number,)
        )[0]
        self.assertEqual(row["custodian_scope"], "person")
        self.assertEqual(row["custodian_key"], "赵六")
        self.assertEqual(row["approval_status"], "已驳回")
        self.assertEqual(row["approval_remark"], "第 2 行数量按人数算多了")
        self.assertFalse(row["claimed_at"])
        # 退回后离开待办：它不是「还没人办」，是「等着改」
        self.assertNotIn(number, [r["ref"] for r in self.service.queue("张三", "化学教研室")])

    def test_return_from_pool_goes_to_requester_not_to_upper_pool(self):
        """组池里的单退回也是回申请人——不存在「退到全院池让别人接」。"""
        number = self._order("r3", scope="department", key="化学教研室", applicant="赵六")
        result = self.service.return_for_revision(
            KIND_ORDER, number, "李四", "这瓶是管制试剂，应先走审批", "化学教研室"
        )
        self.assertTrue(result.is_success(), result.message)
        row = TEST_DB.execute_query(
            "SELECT custodian_scope, custodian_key FROM borrow_order WHERE order_number = ?",
            (number,),
        )[0]
        self.assertEqual(row["custodian_scope"], "person")
        self.assertEqual(row["custodian_key"], "赵六")

    def test_other_department_cannot_return_pool_item(self):
        number = self._order("r4", scope="department", key="化学教研室")
        result = self.service.return_for_revision(
            KIND_ORDER, number, "王五", "x", "生物教研室"
        )
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, RETURN_NOT_MEMBER.upper())

    def test_super_admin_can_return_other_people(self):
        """超管兜底：经办人离职、申请人账号异常时只有他能退。"""
        number = self._order("r5", scope="person", key="张三", applicant="赵六")
        result = self.service.return_for_revision(
            KIND_ORDER, number, "超管", "用途写不清", "生物教研室"
        )
        self.assertTrue(result.is_success(), result.message)

    def test_requirement_sheet_return_sets_status_and_reason(self):
        """需求单退回：状态 returned + 原因落库，且退出在办状态。"""
        number = f"{PREFIX}req-r6"
        TEST_DB.execute_insert(
            "INSERT INTO requirement_sheet (sheet_number, title, requester, status, "
            "custodian_scope, custodian_key) VALUES (?,?,?,?,?,?)",
            (number, "有机合成", "赵六", "submitted", "department", "化学教研室"),
        )
        result = self.service.return_for_revision(
            KIND_REQUIREMENT, number, "李四", "配方浓度填错了", "化学教研室"
        )
        self.assertTrue(result.is_success(), result.message)

        row = TEST_DB.execute_query(
            "SELECT * FROM requirement_sheet WHERE sheet_number = ?", (number,)
        )[0]
        self.assertEqual(row["status"], "returned")
        self.assertEqual(row["return_reason"], "配方浓度填错了")
        self.assertEqual(row["custodian_key"], "赵六")
        self.assertNotIn(
            number, [r["ref"] for r in self.service.queue("李四", "化学教研室")]
        )

    def test_claimed_item_leaves_colleague_queue(self):
        """收窄到人之后，同室同事的待办里就看不见了。"""
        number = self._order("r7", scope="department", key="化学教研室")
        before = [r["ref"] for r in self.service.queue("李四", "化学教研室")]
        self.assertIn(number, before)

        self.service.claim(KIND_ORDER, number, "张三", "化学教研室")
        after = [r["ref"] for r in self.service.queue("李四", "化学教研室")]
        self.assertNotIn(number, after)
        self.assertIn(number, [r["ref"] for r in self.service.queue("张三", "化学教研室")])

    # ---------------------------------------------------------------- 转交
    def test_transfer_requires_admin_target(self):
        number = self._order("t1", scope="person", key="张三")
        bad = self.service.transfer(KIND_ORDER, number, "赵六", "张三")
        self.assertFalse(bad.is_success())
        ok = self.service.transfer(KIND_ORDER, number, "李四", "张三")
        self.assertTrue(ok.is_success(), ok.message)

    def test_transfer_can_target_a_group(self):
        """改派不只能改到人，也能改到组——「这个人不批」的下一步常常是
        「这个组里换个人」。"""
        TEST_DB.execute_insert(
            "INSERT OR IGNORE INTO work_group (name, kind) VALUES (?, ?)",
            ("生物教研室", "department"),
        )
        number = self._order("t2", scope="person", key="张三")
        result = self.service.transfer(KIND_ORDER, number, "group:生物教研室", "张三")
        self.assertTrue(result.is_success(), result.message)
        row = TEST_DB.execute_query(
            "SELECT custodian_scope, custodian_key FROM borrow_order WHERE order_number = ?",
            (number,),
        )[0]
        self.assertEqual(row["custodian_scope"], "department")
        self.assertEqual(row["custodian_key"], "生物教研室")

    def test_requester_can_transfer_own_order(self):
        """申请人也能改派：他被指定的人卡住时，这是他唯一的出口。"""
        number = self._order("t3", scope="person", key="张三", applicant="赵六")
        result = self.service.transfer(KIND_ORDER, number, "李四", "赵六")
        self.assertTrue(result.is_success(), result.message)

    def test_bystander_cannot_transfer(self):
        number = self._order("t4", scope="person", key="张三", applicant="赵六")
        result = self.service.transfer(KIND_ORDER, number, "李四", "王五")
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, "NOT_OWNER")

    # ------------------------------------------------------ 申请人退回（放宽）
    def test_requester_escalates_to_group(self):
        """申请人把单从「某人」放回「某个组」——单还在办，状态一字不动。"""
        number = self._order("e1", scope="person", key="张三", applicant="赵六")
        result = self.service.escalate(KIND_ORDER, number, "赵六")
        self.assertTrue(result.is_success(), result.message)

        row = TEST_DB.execute_query(
            "SELECT * FROM borrow_order WHERE order_number = ?", (number,)
        )[0]
        self.assertEqual(row["custodian_scope"], "department")
        # 赵六的组来自 PEOPLE（化学教研室）——没有成员表时就按主组兜底
        self.assertEqual(row["custodian_key"], "化学教研室")
        # 关键：业务状态没变，单还在待办里
        self.assertEqual(row["approval_status"], "待审批")
        self.assertIn(number, [r["ref"] for r in self.service.queue("李四", "化学教研室")])

    def test_escalate_then_escalate_to_all(self):
        number = self._order("e2", scope="person", key="张三", applicant="赵六")
        self.assertTrue(self.service.escalate(KIND_ORDER, number, "赵六").is_success())
        second = self.service.escalate(KIND_ORDER, number, "赵六")
        self.assertTrue(second.is_success(), second.message)
        row = TEST_DB.execute_query(
            "SELECT custodian_scope FROM borrow_order WHERE order_number = ?", (number,)
        )[0]
        self.assertEqual(row["custodian_scope"], "all")
        # 已经在全院池，再退就没有意义
        third = self.service.escalate(KIND_ORDER, number, "赵六")
        self.assertFalse(third.is_success())

    def test_only_requester_can_escalate(self):
        """管理员不能替申请人放弃「指定」——那是申请人的决定权。"""
        number = self._order("e3", scope="person", key="张三", applicant="赵六")
        result = self.service.escalate(KIND_ORDER, number, "张三")
        self.assertFalse(result.is_success())
        self.assertEqual(result.error_code, RETURN_NOT_REQUESTER.upper())

    def test_escalate_to_named_group(self):
        """同时属于多个组时，放给哪个组由申请人自己选。"""
        TEST_DB.execute_insert(
            "INSERT OR IGNORE INTO work_group (name, kind) VALUES (?, ?)",
            ("生物教研室", "research"),
        )
        number = self._order("e4", scope="person", key="张三", applicant="赵六")
        result = self.service.escalate(
            KIND_ORDER, number, "赵六", target_group="生物教研室"
        )
        self.assertTrue(result.is_success(), result.message)
        row = TEST_DB.execute_query(
            "SELECT custodian_key FROM borrow_order WHERE order_number = ?", (number,)
        )[0]
        self.assertEqual(row["custodian_key"], "生物教研室")

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
