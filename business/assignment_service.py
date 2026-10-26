"""单据归属业务：算目标、落库、认领、退回、转交。

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
3. **退回只能放宽**。认领来的单退回原处，指定来的单降一级。同教研室的其他
   管理员无权退——见 `domain.assignment`。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from domain.assignment import (
    CLAIM_ASSIGNED,
    CLAIM_NOT_ALLOWED,
    CLAIM_OTHER_DEPARTMENT,
    CLAIM_TAKEN,
    RELEASE_NOT_OWNER,
    RELEASE_NOT_PERSON,
    RELEASE_ROOT,
    Assignment,
    assignment_of,
    claimed_from_of,
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
    # 退回 / 转交
    # ------------------------------------------------------------------
    @handle_exception(context="退回池")
    def release(self, kind: str, ref: str, me: str, my_department: str = "") -> ServiceResult:
        """把单从某人名下放回池里。

        权限只有两种人：当前接单人本人、超管。**同教研室的其他管理员不在
        其中**——组内可见是为了不漏单，不代表组内互相可以改归属。旁人代退
        是替当事人做决定，而「他干不了这件」只有当事人知道。
        """
        row = self.issues.row(kind, ref)
        if not row:
            return ServiceResult.fail(message=f"单据不存在：{ref}", error_code="NOT_FOUND")

        current = assignment_of(row)
        is_super = self.is_super_admin(me)
        if not current.is_person:
            return ServiceResult.fail(
                message="这张单还没到人手上，没有「退回」这个动作",
                error_code=RELEASE_NOT_PERSON.upper(),
            )
        if not current.can_release(me, is_super_admin=is_super):
            return ServiceResult.fail(
                message=f"只有 {current.key} 本人或超级管理员可以退回这张单",
                error_code=RELEASE_NOT_OWNER.upper(),
            )

        target = current.after_release(
            my_department or self.department_of(me), claimed_from_of(row)
        )
        if target is None:
            return ServiceResult.fail(
                message="这张单已经在全院池，退无可退", error_code=RELEASE_ROOT.upper()
            )

        changed = self.issues.release(kind, ref, target.scope, target.key, current.key)
        if not changed:
            return ServiceResult.fail(
                message="这张单刚被改动过，请刷新后再试", error_code="STALE"
            )
        audit(me, "退回池", _table_of(kind), ref, f"{current.key} → {target.describe()}")
        return ServiceResult.ok(
            data={"kind": kind, "ref": ref, "custodian_scope": target.scope,
                  "custodian_key": target.key},
            message=f"已退回：{target.describe()}",
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
