"""单据归属业务：算目标、落库、认领、退回修改、转交。

这里补的是 BCLRM 一直缺的那一环：**单据有主**。

原来的隐含规则是「全院都能看见、谁点谁办」。工单实际上不是这么走的——每门
课对应一个管理员，教研室里的申请也往往指定提交人。于是「抢单」不是主问题，
「这单归谁」才是。归属算不出来的时候也不能报错（老师会被卡在提交按钮上），
而是三级降级：指定人 → 教研室池 → 全院池。

三条边界：

1. **归属先在 `business/` 这一层落库**，`capabilities/circulation/routing.py`
   一行不改。路由的「配错了必须显式失败」和归属的「总能落一处」是两件事，
   混在一起会让 `RoutingError` 失去信号意义。
2. **认领是一条带条件的 UPDATE**，`rowcount=0` 就是判定结果，不需要事务外
   加锁、不需要租约。判定点放在写，不放在读。
3. **权限跟着当前归属走，不跟历史走**。收窄到人，别人当场看不见也动不了；
   放宽回组，组里每个人当场看得见、办得动、退得动（见 `domain.assignment`）。

一个容易被搞混的分工：**退回不是「我不接」，是「这单要改」**。手上没料的
管理员去发起调配，单留在他名下；退回只用于单本身有问题，落点永远是申请人。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from domain.assignment import (
    ACT_NOT_MEMBER,
    CLAIM_ASSIGNED,
    CLAIM_NOT_ALLOWED,
    CLAIM_OTHER_DEPARTMENT,
    CLAIM_TAKEN,
    RETURN_INVALID_STATE,
    RETURN_NOT_MEMBER,
    RETURN_NO_REASON,
    Assignment,
    assignment_of,
)
from services.base.person_service import person_service
from services.core.issue_queue_service import (
    KIND_ORDER,
    KIND_REQUIREMENT,
    IssueQueueService,
)
from services.custodian_route import SCOPE_COURSE, custodian_route_repository
from utils.audit import audit
from utils.error_handler import ServiceResult, handle_exception, logger

KIND_LABELS = {
    KIND_ORDER: "领用工单",
    KIND_REQUIREMENT: "需求单",
}

#: 工单只有「待审批」才需要管理员动手。无需审批的工单在创建时就已经
#: 扣了库存、发了料，它不该出现在待办里——那不叫待办，叫已完成。
ORDER_PENDING_APPROVAL = "待审批"

#: 需求单在办状态。``partial`` 也要算：一部分行兑完了，剩下的还在等料。
REQUIREMENT_OPEN_STATUSES = ("submitted", "partial")


class AssignmentService:
    """归属与队列。"""

    def __init__(self, database=None, routes=None, people=None, issues=None) -> None:
        self.issues = issues or IssueQueueService(database)
        self.routes = routes or custodian_route_repository
        self.people = people or person_service

    # ------------------------------------------------------------------
    # 人员属性：一律现查，不信 session
    # ------------------------------------------------------------------
    def department_of(self, name: str) -> str:
        """当前科室。

        **不能信 session**：科室会调岗，登录时那份可能是去年的。待办过滤
        靠它，错了就是「该看的看不见」。
        """
        name = (name or "").strip()
        if not name:
            return ""
        try:
            person = self.people.get_by_name(name)
        except Exception as exc:  # 库还没初始化
            logger.warning(f"查询人员科室失败：{exc}")
            return ""
        return (getattr(person, "department", "") or "").strip() if person else ""

    def role_of(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        try:
            person = self.people.get_by_name(name)
        except Exception:
            return ""
        return (getattr(person, "role", "") or "").strip() if person else ""

    def is_super_admin(self, name: str) -> bool:
        return self.role_of(name) == "super_admin"

    def is_admin(self, name: str) -> bool:
        return self.role_of(name) in ("admin", "super_admin")

    def admin_names(self) -> List[str]:
        """可以当「指定受理人」或「转交对象」的人（只列管理员）。"""
        try:
            persons = self.people.get_all_persons()
        except Exception:
            return []
        return sorted(
            p.name
            for p in persons
            if (getattr(p, "role", "") or "") in ("admin", "super_admin")
        )

    # ------------------------------------------------------------------
    # 算归属：课程 → 科室 → 全院
    # ------------------------------------------------------------------
    def resolve_target(self, requester: str, source_code: str = "") -> Assignment:
        """这张单该归谁。三级降级，最后一级是 ``all``，不报错。

        第一层：课程/项目路由命中 → 指定给那个管理员。命中逻辑与
        ``SourceRouter._lookup`` 同构（先整键、再退到课程名），但这里不构造
        ``TeacherRequest``——落归属的时候工单路径根本没有需求单，硬造一个
        空壳对象比多写十行匹配更危险。
        第二层：申请人有登记的教研室 → 归教研室池。**不落到「该室默认的
        那个管理员」**，否则第二层就退化成第一层，组池失去意义。
        第三层：都没有 → 全院池。
        """
        course_rules = self.routes.rules(SCOPE_COURSE, self.department_of)
        matched = self._match_course(course_rules, source_code)
        if matched is not None:
            return Assignment.person(matched)

        department = self.department_of(requester)
        if department:
            return Assignment.department(department)
        return Assignment.everywhere()

    @staticmethod
    def _match_course(rules: Dict[str, Any], source_code: str) -> Optional[str]:
        """两级匹配：整键 → 课程名（``课程/班级`` 的前半）。"""
        code = (source_code or "").strip()
        if not code:
            return None
        matched = rules.get(code) or rules.get(code.split("/")[0])
        return matched.name if matched is not None else None

    # ------------------------------------------------------------------
    # 落归属
    # ------------------------------------------------------------------
    def assign(self, kind: str, ref: str, assignment: Assignment, operator: str = "") -> bool:
        """把归属写到单据上（只在创建/受理时用，之后靠认领改）。"""
        changed = self.issues.set_assignment(kind, ref, assignment.scope, assignment.key)
        if changed and operator:
            logger.info(f"{KIND_LABELS.get(kind, kind)} {ref} 归属 → {assignment.describe()}")
        return bool(changed)

    def assign_for_sheet(self, sheet_number: str) -> Optional[Assignment]:
        """需求单落库后补归属：读它自己的申请人 + 来源编码。"""
        row = self.issues.row(KIND_REQUIREMENT, sheet_number)
        if not row:
            return None
        assignment = self.resolve_target(
            row.get("requester") or "", row.get("source_code") or ""
        )
        self.assign(KIND_REQUIREMENT, sheet_number, assignment)
        return assignment

    def assign_for_order(
        self, order_number: str, requester: str, source_code: str = ""
    ) -> Optional[Assignment]:
        assignment = self.resolve_target(requester, source_code)
        self.assign(KIND_ORDER, order_number, assignment)
        return assignment

    # ------------------------------------------------------------------
    # 认领
    # ------------------------------------------------------------------
    @handle_exception(context="接单")
    def claim(
        self, kind: str, ref: str, me: str, my_department: str = ""
    ) -> ServiceResult:
        """把归属从组/池收窄到人。

        `rowcount=0` 有三种原因，提示必须分开——用户要看见「这单被谁拿走了」，
        不是一个红叉。
        """
        row = self.issues.row(kind, ref)
        if not row:
            return ServiceResult.fail(message=f"单据不存在：{ref}", error_code="NOT_FOUND")

        if not self.is_admin(me):
            return ServiceResult.fail(
                message="只有管理员可以接单", error_code="NOT_ADMIN"
            )

        current = assignment_of(row)
        is_super = self.is_super_admin(me)
        if not current.can_claim(me, my_department, is_super_admin=is_super):
            reason, message = self._claim_blocked(row, current, me, my_department)
            return ServiceResult.fail(message=message, error_code=reason.upper())

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        changed = self.issues.claim(
            kind,
            ref,
            me,
            row.get("custodian_scope") or "",
            row.get("custodian_key") or "",
            now,
        )
        if not changed:
            # 读到的状态已经不是库里的状态了：有人抢先一步。重新读一次再判断
            # 原因，而不是笼统报「失败」。
            fresh = self.issues.row(kind, ref) or {}
            reason, message = self._claim_blocked(
                fresh, assignment_of(fresh), me, my_department
            )
            return ServiceResult.fail(message=message, error_code=reason.upper())

        audit(me, "接单", _table_of(kind), ref,
              f"归属 → {Assignment.person(me).describe()}")
        return ServiceResult.ok(
            data={"kind": kind, "ref": ref, "custodian_scope": "person",
                  "custodian_key": me},
            message=f"已接单：{ref}",
        )

    def _claim_blocked(
        self, row: Dict[str, Any], current: Assignment, me: str, my_department: str
    ):
        """认领被拒的原因与提示。"""
        if current.is_person:
            if (row.get("claimed_at") or "") and current.key != me:
                return CLAIM_TAKEN, f"这张单已被 {current.key} 接走"
            if current.key == me:
                return CLAIM_NOT_ALLOWED, "这张单已经在您名下"
            return CLAIM_ASSIGNED, f"这张单指定由 {current.key} 受理"
        if current.is_department and current.key != (my_department or "").strip():
            return CLAIM_OTHER_DEPARTMENT, f"这张单归 {current.key}，你接不了"
        return CLAIM_NOT_ALLOWED, "当前状态不能接单"

    # ------------------------------------------------------------------
    # 能不能看 / 能不能办
    # ------------------------------------------------------------------
    def assignment_for(self, kind: str, ref: str) -> Optional[Assignment]:
        row = self.issues.row(kind, ref)
        return assignment_of(row) if row else None

    def explicit_assignment(self, kind: str, ref: str) -> Optional[Assignment]:
        """库里**真的写了**归属吗。空返回 ``None``（升级前的老单）。

        为什么要留这个区分：``assignment_of`` 把空规范成 ``all`` 是为了显示
        和过滤（老单不能从待办里消失），但「没登记归属」不等于「登记成全院
        池」。老单的审批权仍按原字段 ``approver`` 判——不能凭空给老单换一个
        更宽的主人，那是借兼容之名放宽权限。
        """
        row = self.issues.row(kind, ref)
        if not row:
            return None
        if not (row.get("custodian_scope") or "").strip():
            return None
        return assignment_of(row)

    def can_see(self, kind: str, ref: str, me: str) -> bool:
        """这张单该不该出现在我的任何列表里。

        收窄到人之后，同室的其他人也看不见——这不是隐私偏好，是「谁负责」
        这件事必须只有一个答案：一张单同时挂在两个人眼前，两个人都会以为
        对方在办。
        """
        if self.is_super_admin(me):
            return True
        row = self.issues.row(kind, ref)
        if not row:
            return False
        return assignment_of(row).visible_to(me, self.department_of(me))

    def can_handle(self, kind: str, ref: str, me: str):
        """能不能办这张单的业务动作。返回 ``(bool, 提示语)``。

        页面用它决定给不给按钮，服务端用它拦写入——两处用同一个判定，才
        不会出现「按钮是灰的但接口能调」。
        """
        row = self.issues.row(kind, ref)
        if not row:
            return False, f"单据不存在：{ref}"
        current = assignment_of(row)
        allowed = current.can_handle(
            me,
            self.department_of(me),
            is_admin=self.is_admin(me),
            is_super_admin=self.is_super_admin(me),
        )
        return (True, "") if allowed else (False, current.handle_blocked_message())

    # ------------------------------------------------------------------
    # 退回修改 / 转交
    # ------------------------------------------------------------------
    @staticmethod
    def requester_of(kind: str, row: Dict[str, Any]) -> str:
        """申请人。两张表字段不同名，收在一处，别到处写 ``if kind ==``。"""
        key = "applicant" if kind == KIND_ORDER else "requester"
        return (row.get(key) or "").strip()

    @handle_exception(context="退回修改")
    def return_for_revision(
        self, kind: str, ref: str, me: str, reason: str = "", my_department: str = ""
    ) -> ServiceResult:
        """退单要申请人改。**落点恒为申请人**，不是任何池。

        理由见 ``domain.assignment``：手上没料是调配的事，单不动；单要退，一
        定是单本身有问题（数量、瓶、用途、课程），只有申请人能改。所以退回
        不带「给谁办」的含义，不需要挑接收人，也不存在「退到上一级池」。

        权限是当前归属的成员集合（能办的人才能退）+ 超管兜底。
        """
        row = self.issues.row(kind, ref)
        if not row:
            return ServiceResult.fail(message=f"单据不存在：{ref}", error_code="NOT_FOUND")

        reason = (reason or "").strip()
        if not reason:
            return ServiceResult.fail(
                message="退回必须写原因：申请人要知道改哪里，否则退回等于石沉大海",
                error_code=RETURN_NO_REASON.upper(),
            )

        current = assignment_of(row)
        my_department = (my_department or self.department_of(me) or "").strip()
        if not current.can_return(
            me,
            my_department,
            is_admin=self.is_admin(me),
            is_super_admin=self.is_super_admin(me),
        ):
            return ServiceResult.fail(
                message=current.handle_blocked_message(), error_code=RETURN_NOT_MEMBER.upper()
            )

        requester = self.requester_of(kind, row)
        if not requester:
            return ServiceResult.fail(
                message="这张单没有申请人，退不回去", error_code="NO_REQUESTER"
            )
        if requester == me:
            return ServiceResult.fail(
                message="这是你自己提交的单，有问题请直接改单重提", error_code="SELF_RETURN"
            )

        changed = self.issues.return_to_requester(
            kind, ref, requester, reason, current.scope, current.key
        )
        if not changed:
            return ServiceResult.fail(
                message="这张单刚被改动过，或已经办结，请刷新后再看",
                error_code=RETURN_INVALID_STATE.upper(),
            )
        audit(
            me,
            "退回修改",
            _table_of(kind),
            ref,
            f"{current.describe()} → 退回 {requester} 修改：{reason}",
        )
        return ServiceResult.ok(
            data={
                "kind": kind,
                "ref": ref,
                "requester": requester,
                "custodian_scope": "person",
                "custodian_key": requester,
                "return_reason": reason,
            },
            message=f"已退回 {requester} 修改：{reason}",
        )

    @handle_exception(context="转交")
    def transfer(
        self, kind: str, ref: str, target_name: str, me: str
    ) -> ServiceResult:
        """把单转给另一个管理员（来源不变，只换人）。"""
        row = self.issues.row(kind, ref)
        if not row:
            return ServiceResult.fail(message=f"单据不存在：{ref}", error_code="NOT_FOUND")
        current = assignment_of(row)
        is_super = self.is_super_admin(me)
        if not current.can_transfer(me, is_super_admin=is_super):
            return ServiceResult.fail(
                message=f"只有 {current.key} 本人或超级管理员可以转交这张单",
                error_code="NOT_OWNER",
            )
        target_name = (target_name or "").strip()
        if not target_name:
            return ServiceResult.fail(message="请选择转交对象", error_code="EMPTY_TARGET")
        if not self.is_admin(target_name):
            return ServiceResult.fail(
                message=f"{target_name} 不是管理员，不能受理单据",
                error_code="INVALID_TARGET",
            )
        if target_name == current.key:
            return ServiceResult.fail(
                message="这张单已经在这个人名下", error_code="SAME_TARGET"
            )

        changed = self.issues.transfer(kind, ref, target_name, current.key)
        if not changed:
            return ServiceResult.fail(
                message="这张单刚被改动过，请刷新后再试", error_code="STALE"
            )
        audit(me, "转交单据", _table_of(kind), ref, f"{current.key} → {target_name}")
        return ServiceResult.ok(
            data={"kind": kind, "ref": ref, "custodian_key": target_name},
            message=f"已转交给 {target_name}",
        )

    # ------------------------------------------------------------------
    # 队列
    # ------------------------------------------------------------------
    def queue(
        self,
        me: str,
        my_department: str = "",
        kinds: Optional[tuple] = None,
        limit: int = 300,
    ) -> List[Dict[str, Any]]:
        """当前用户该看到的在办单，按提交时间升序。"""
        return self.issues.open_rows(
            me,
            my_department,
            is_super_admin=self.is_super_admin(me),
            kinds=kinds,
            limit=limit,
        )

    def queue_summary(self, me: str, my_department: str = "") -> Dict[str, int]:
        """三档计数，页面顶部的 KPI 用。"""
        rows = self.queue(me, my_department)
        mine = department = pool = 0
        for row in rows:
            scope = (row.get("custodian_scope") or "").strip()
            key = (row.get("custodian_key") or "").strip()
            if scope == "person" and key == (me or ""):
                mine += 1
            elif scope == "department" and (my_department or "") and key == my_department:
                department += 1
            else:
                pool += 1
        return {"mine": mine, "department": department, "pool": pool, "total": len(rows)}


def _table_of(kind: str) -> str:
    """审计日志里的目标表名（与 services 层的映射保持一致）。"""
    from services.core.issue_queue_service import TABLES

    return TABLES.get(kind, (kind, ""))[0]


assignment_service = AssignmentService()

__all__ = [
    "AssignmentService",
    "assignment_service",
    "KIND_ORDER",
    "KIND_REQUIREMENT",
    "KIND_LABELS",
    "ORDER_PENDING_APPROVAL",
    "REQUIREMENT_OPEN_STATUSES",
]
