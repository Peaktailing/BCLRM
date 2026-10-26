"""单据归属业务：算目标、落库、认领、退回、放宽、改派。

这里补的是 BCLRM 一直缺的那一环：**单据有主**。

原来的隐含规则是「全院都能看见、谁点谁办」。工单实际上不是这么走的——每门
课对应一个管理员，教研室里的申请也往往指定提交人。于是「抢单」不是主问题，
「这单归谁」才是。归属算不出来的时候也不能报错（老师会被卡在提交按钮上），
而是三级降级：指定人 → 组 → 全院。

四条边界：

1. **归属先在 `business/` 这一层落库**，`capabilities/circulation/routing.py`
   一行不改。路由的「配错了必须显式失败」和归属的「总能落一处」是两件事，
   混在一起会让 `RoutingError` 失去信号意义。
2. **认领是一条带条件的 UPDATE**，`rowcount=0` 就是判定结果，不需要事务外
   加锁、不需要租约。判定点放在写，不放在读。
3. **权限跟着当前归属走，不跟历史走**。收窄到人，别人当场看不见也动不了；
   放宽回组，组里每个人当场看得见、办得动、退得动（见 `domain.assignment`）。
4. **「组」是一等公民**：一个人可以同时属于教研室和科研组，组之间会交叉。
   判定一律用「我所属的全部组」这个集合，不是 `person.department` 那一列。

三个容易混的动作，主体和方向都不同：

============  ==========  ==========================================
动作           谁做         做什么
============  ==========  ==========================================
退回修改        管理员       单有问题，退给申请人改（单离开在办）
退回上一层      申请人       指定的人不批，放给全组、再放给全院（单还在办）
改派            持有人/申请人  换一个人或换一个组办（单还在办）
============  ==========  ==========================================

手上没料既不是退回也不是改派：**做调配**，单留在他名下。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from domain.assignment import (
    ACT_NOT_MEMBER,
    CLAIM_ASSIGNED,
    CLAIM_NOT_ALLOWED,
    CLAIM_OTHER_DEPARTMENT,
    CLAIM_TAKEN,
    RETURN_INVALID_STATE,
    RETURN_NOT_MEMBER,
    RETURN_NOT_REQUESTER,
    RETURN_ROOT,
    Assignment,
    assignment_of,
)
from services.base.person_service import person_service
from services.base.work_group_service import GROUP_KIND_LABELS, work_group_service
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

    def __init__(
        self, database=None, routes=None, people=None, issues=None, groups=None
    ) -> None:
        self.issues = issues or IssueQueueService(database)
        self.routes = routes or custodian_route_repository
        self.people = people or person_service
        self.groups = groups or work_group_service

    # ------------------------------------------------------------------
    # 人员属性：一律现查，不信 session
    # ------------------------------------------------------------------
    def department_of(self, name: str) -> str:
        """主组（``person.department``）。

        **不能信 session**：科室会调岗，登录时那份可能是去年的。待办过滤
        靠它，错了就是「该看的看不见」。

        注意：这是**主组**，不是全部。判权一律用 :meth:`groups_of`——一个人
        可能同时属于教研室和科研组，用一列去判会把另一个组池的单漏掉。
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

    def groups_of(self, name: str) -> List[str]:
        """这个人所属的全部组（教研室 + 科研组 + 其他）。

        成员表是唯一口径，``person.department`` 只在成员表查不到时兜底。
        兜底走 :meth:`department_of`（注入的人员目录）而不是直接读库，是因为
        人员目录本身也可能是外部实现——两处都查不到才算「没有组」。
        """
        try:
            groups = self.groups.groups_of(name)
        except Exception as exc:
            logger.warning(f"查询组成员失败：{exc}")
            groups = []
        if groups:
            return groups
        department = self.department_of(name)
        return [department] if department else []

    def primary_group(self, name: str) -> str:
        """主组：路由与「默认提交到哪个组」用。

        优先 ``person.department``（人自己登记的那个），不在就取组名排序后
        第一个——排序是为了让同一份数据每次算出同一个结果，不是因为在业务上
        「第一个」更正确。
        """
        groups = self.groups_of(name)
        if not groups:
            return ""
        department = self.department_of(name)
        if department and department in groups:
            return department
        return sorted(groups)[0]

    def group_label(self, group_name: str) -> str:
        """``化学教研室（教研室）``——队列里要让人看出这是哪种组。"""
        try:
            return self.groups.describe(group_name)
        except Exception:
            return group_name

    def group_kind_of(self, group_name: str) -> str:
        try:
            return self.groups.kind_of(group_name)
        except Exception:
            return ""

    @staticmethod
    def _normalize_groups(my_groups: Any) -> List[str]:
        if my_groups is None:
            return []
        if isinstance(my_groups, str):
            value = my_groups.strip()
            return [value] if value else []
        return [str(g).strip() for g in my_groups if str(g or "").strip()]

    def _groups_arg(self, me: str, my_groups: Any = None) -> List[str]:
        """判定用的组集合。

        **库里查到的优先**，调用方传进来的只是兜底：页面传的是 session 里的
        科室，那份可能是调岗之前留下的。数据库说得清就不听缓存。
        """
        groups = self.groups_of(me)
        if groups:
            return groups
        return self._normalize_groups(my_groups)

    def group_options(self) -> List[Dict[str, Any]]:
        """可选的全部组（带成员数与类型标签），页面下拉用。"""
        try:
            groups = self.groups.list_groups()
        except Exception as exc:
            logger.warning(f"读取管理组失败：{exc}")
            return []
        for group in groups:
            group["label"] = (
                f"{group['name']}（{GROUP_KIND_LABELS.get(group.get('kind'), '组')}）"
                f"· {group.get('member_count') or 0} 人"
            )
        return groups

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
    # 算归属：课程 → 组 → 全院
    # ------------------------------------------------------------------
    def resolve_target(self, requester: str, source_code: str = "") -> Assignment:
        """这张单该归谁。三级降级，最后一级是 ``all``，不报错。

        第一层：课程/项目路由命中 → 指定给那个管理员。命中逻辑与
        ``SourceRouter._lookup`` 同构（先整键、再退到课程名），但这里不构造
        ``TeacherRequest``——落归属的时候工单路径根本没有需求单，硬造一个
        空壳对象比多写十行匹配更危险。
        第二层：申请人有所属的组 → 归该组。**不落到「该组默认的那个管理
        员」**，否则第二层就退化成第一层，组池失去意义。
        第三层：都没有 → 全院池。

        第二层取的是**主组**：一个人可能既在教研室又在科研组，自动挑一个
        没有依据。要进别的组，申请人提交时自己选（见 ``submit_group``）。
        """
        course_rules = self.routes.rules(SCOPE_COURSE, self.department_of)
        matched = self._match_course(course_rules, source_code)
        if matched is not None:
            return Assignment.person(matched)

        group = self.primary_group(requester)
        if group:
            return Assignment.department(group)
        return Assignment.everywhere()

    def resolve_target_for_group(self, requester: str, group_name: str) -> Assignment:
        """申请人自己选了组：直接落那个组，不再降级。

        只在「这个人确实是该组成员」时生效——否则谁都能把单丢到任意组，
        组池就变成公厕了。不是成员就退回三级降级。
        """
        group_name = (group_name or "").strip()
        if group_name and group_name in self.groups_of(requester):
            return Assignment.department(group_name)
        return self.resolve_target(requester)

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
        self, kind: str, ref: str, me: str, my_groups: Any = ""
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

        groups = self._groups_arg(me, my_groups)
        current = assignment_of(row)
        is_super = self.is_super_admin(me)
        if not current.can_claim(me, groups, is_super_admin=is_super):
            reason, message = self._claim_blocked(row, current, me, groups)
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
                fresh, assignment_of(fresh), me, groups
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
        self, row: Dict[str, Any], current: Assignment, me: str, groups: Sequence[str]
    ):
        """认领被拒的原因与提示。"""
        if current.is_person:
            if (row.get("claimed_at") or "") and current.key != me:
                return CLAIM_TAKEN, f"这张单已被 {current.key} 接走"
            if current.key == me:
                return CLAIM_NOT_ALLOWED, "这张单已经在您名下"
            return CLAIM_ASSIGNED, f"这张单指定由 {current.key} 受理"
        if current.is_department and current.key not in [g for g in groups if g]:
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
        return assignment_of(row).visible_to(me, self._groups_arg(me))

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
            self._groups_arg(me),
            is_admin=self.is_admin(me),
            is_super_admin=self.is_super_admin(me),
        )
        return (True, "") if allowed else (False, current.handle_blocked_message())

    # ------------------------------------------------------------------
    # 退回修改
    # ------------------------------------------------------------------
    @staticmethod
    def requester_of(kind: str, row: Dict[str, Any]) -> str:
        """申请人。两张表字段不同名，收在一处，别到处写 ``if kind ==``。"""
        key = "applicant" if kind == KIND_ORDER else "requester"
        return (row.get(key) or "").strip()

    @handle_exception(context="退回修改")
    def return_for_revision(
        self, kind: str, ref: str, me: str, reason: str = "", my_groups: Any = ""
    ) -> ServiceResult:
        """退单要申请人改。**落点恒为申请人**，不是任何池。

        理由见 ``domain.assignment``：手上没料是调配的事，单不动；单要退，一
        定是单本身有问题（数量、瓶、用途、课程），只有申请人能改。所以退回
        不带「给谁办」的含义，不需要挑接收人，也不存在「退到上一级池」。

        权限是当前归属的成员集合（能办的人才能退）+ 超管兜底。

        **原因不是必填**：退这个动作本身已经说明「这张单不能按现在这样批」，
        具体哪里不对由两个人当面说清。强迫填一句话只会得到一百条「再改改」，
        既没信息量，又把申请人挡在门外。填了照样存下来，方便留痕。
        """
        row = self.issues.row(kind, ref)
        if not row:
            return ServiceResult.fail(message=f"单据不存在：{ref}", error_code="NOT_FOUND")

        reason = (reason or "").strip()
        groups = self._groups_arg(me, my_groups)
        current = assignment_of(row)
        if not current.can_return(
            me,
            groups,
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
            f"{current.describe()} → 退回 {requester} 修改"
            + (f"：{reason}" if reason else ""),
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
            message=f"已退回 {requester} 修改" + (f"：{reason}" if reason else ""),
        )

    # ------------------------------------------------------------------
    # 申请人退回（放宽归属）
    # ------------------------------------------------------------------
    @handle_exception(context="退回给组")
    def escalate(
        self, kind: str, ref: str, me: str, target_group: str = ""
    ) -> ServiceResult:
        """申请人把单放给更多人办：人 → 组 → 全院。

        这不是「退单要改」，单原封不动，业务状态一个字段都不碰——只是「指定
        的那个人一直不批，别再等他了」。所以权限也不是管理员那套：**只有申
        请人本人**（超管兜底），因为「要不要放弃指定」是他对自己那张单的决定。

        ``target_group`` 用于「我同时属于教研室和科研组，这次想给科研组看」。
        不指定就放回主组。
        """
        row = self.issues.row(kind, ref)
        if not row:
            return ServiceResult.fail(message=f"单据不存在：{ref}", error_code="NOT_FOUND")

        current = assignment_of(row)
        requester = self.requester_of(kind, row)
        is_super = self.is_super_admin(me)
        if not current.can_escalate(me, requester, is_super_admin=is_super):
            if current.is_all:
                return ServiceResult.fail(
                    message="这张单已经在全院池，全院管理员都能接",
                    error_code=RETURN_ROOT.upper(),
                )
            return ServiceResult.fail(
                message="只有申请人本人可以把自己的单放给别人办",
                error_code=RETURN_NOT_REQUESTER.upper(),
            )

        groups = self._groups_arg(requester or me)
        target = current.escalated_to(groups, target_group)
        if target is None:
            return ServiceResult.fail(
                message="这张单已经在全院池，退无可退", error_code=RETURN_ROOT.upper()
            )
        if target.scope == current.scope and target.key == current.key:
            return ServiceResult.fail(
                message="这张单已经在那个组里了", error_code="SAME_TARGET"
            )

        changed = self.issues.escalate(
            kind, ref, target.scope, target.key, current.scope, current.key
        )
        if not changed:
            return ServiceResult.fail(
                message="这张单刚被改动过，请刷新后再看", error_code="STALE"
            )
        audit(
            me,
            "退回给组" if target.is_department else "退回全院池",
            _table_of(kind),
            ref,
            f"{current.describe()} → {target.describe()}",
        )
        return ServiceResult.ok(
            data={
                "kind": kind,
                "ref": ref,
                "custodian_scope": target.scope,
                "custodian_key": target.key,
            },
            message=f"已放给：{target.describe()}",
        )

    # ------------------------------------------------------------------
    # 改派
    # ------------------------------------------------------------------
    @handle_exception(context="改派")
    def transfer(self, kind: str, ref: str, target: str, me: str) -> ServiceResult:
        """把单改派给另一个人，或另一个组。

        ``target`` 支持三种写法：``person:张三`` / ``group:化学教研室`` /
        裸名字（先按组名认，再按人名认）。允许改派到组，是因为「这个人不批」
        的下一步很可能不是「换一个人」而是「换一个组」——课题组之间本来就
        交叉，指错了组的单该放给对的那个组，而不是硬塞给某个人。

        权限：当前持有人（``person`` 层本人）、申请人、超管。申请人也在内是
        必须的——他被指定的人卡住时，改派是他唯一的出口。
        """
        row = self.issues.row(kind, ref)
        if not row:
            return ServiceResult.fail(message=f"单据不存在：{ref}", error_code="NOT_FOUND")

        current = assignment_of(row)
        requester = self.requester_of(kind, row)
        is_super = self.is_super_admin(me)
        if not current.can_transfer(me, requester, is_super_admin=is_super):
            return ServiceResult.fail(
                message="只有当前受理人、申请人和超级管理员可以改派这张单",
                error_code="NOT_OWNER",
            )

        wanted = self.resolve_target_ref(target)
        if wanted is None:
            return ServiceResult.fail(
                message=f"找不到受理方：{target}", error_code="INVALID_TARGET"
            )
        if not current.can_transfer_to(wanted):
            return ServiceResult.fail(
                message=(
                    "已经在那个受理方名下了" if not wanted.is_all
                    else "要放给全院请用「退回给全院」，改派必须指明人或组"
                ),
                error_code="SAME_TARGET",
            )

        changed = self.issues.transfer(
            kind, ref, wanted.scope, wanted.key, current.scope, current.key
        )
        if not changed:
            return ServiceResult.fail(
                message="这张单刚被改动过，请刷新后再试", error_code="STALE"
            )
        audit(
            me, "改派", _table_of(kind), ref, f"{current.describe()} → {wanted.describe()}"
        )
        return ServiceResult.ok(
            data={
                "kind": kind,
                "ref": ref,
                "custodian_scope": wanted.scope,
                "custodian_key": wanted.key,
            },
            message=f"已改派：{wanted.describe()}",
        )

    def resolve_target_ref(self, target: str) -> Optional[Assignment]:
        """把页面传来的目标解析成归属。

        三种写法都要认，因为下拉框里人和组混在一起：``person:张三``、
        ``group:化学教研室``、裸名字。裸名字先按组认——组名通常更长更具体，
        撞名的概率比人名低；认组失败再按管理员人名认。
        """
        raw = (target or "").strip()
        if not raw:
            return None
        if raw.startswith("person:"):
            name = raw.split(":", 1)[1].strip()
            return Assignment.person(name) if name and self.is_admin(name) else None
        if raw.startswith("group:"):
            name = raw.split(":", 1)[1].strip()
            return Assignment.department(name) if name and self.groups.exists(name) else None
        if self.groups.exists(raw):
            return Assignment.department(raw)
        if self.is_admin(raw):
            return Assignment.person(raw)
        return None

    def transfer_options(self) -> List[Tuple[str, str]]:
        """改派下拉框的选项：``[(值, 显示文字)]``，人和组混排。

        组排在前面：改派到组比改派到人更常用（换个人不批的概率比换一组人
        高），而且组名自带类型标签，看得懂。
        """
        options: List[Tuple[str, str]] = []
        for group in self.group_options():
            options.append(
                (f"group:{group['name']}", f"👥 {group['label']}")
            )
        for name in self.admin_names():
            options.append((f"person:{name}", f"👤 {name}"))
        return options

    # ------------------------------------------------------------------
    # 队列
    # ------------------------------------------------------------------
    def queue(
        self,
        me: str,
        my_groups: Any = "",
        kinds: Optional[tuple] = None,
        limit: int = 300,
    ) -> List[Dict[str, Any]]:
        """当前用户该看到的在办单，按提交时间升序。"""
        return self.issues.open_rows(
            me,
            self._groups_arg(me, my_groups),
            is_super_admin=self.is_super_admin(me),
            kinds=kinds,
            limit=limit,
        )

    def my_open_sheets(self, requester: str) -> List[Dict[str, Any]]:
        """我提交的、还在办的需求单（不看收件人是谁）。"""
        return self.issues.open_sheets_of_requester(requester)

    def queue_summary(self, me: str, my_groups: Any = "") -> Dict[str, int]:
        """四档计数，页面顶部的 KPI 用。

        ``department`` 是「我所在的那些组」的合计——一个人同时在教研室和
        科研组时，两个池的单都会落到这一档，分不出也不必分：对他来说都是
        「我的组的活」。
        """
        groups = set(self._groups_arg(me, my_groups))
        rows = self.queue(me, my_groups)
        mine = department = pool = 0
        for row in rows:
            scope = (row.get("custodian_scope") or "").strip()
            key = (row.get("custodian_key") or "").strip()
            if scope == "person" and key == (me or ""):
                mine += 1
            elif scope == "department" and key in groups:
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
