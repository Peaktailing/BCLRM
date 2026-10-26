"""单据归属：这一张单该谁受理。

BCLRM 原来只有一条「全院都能看见、谁点谁办」的隐含规则。真实业务里工单
本来就有主：每门课对应一个管理员，教研室里的申请也往往指定提交人。于是
「抢单」不是主问题，**「归属算不算得出来、算不出来往哪落」**才是。

三层降级，每一层都是明确配置，不存在猜：

===========  ========================  ============================
层级          归属标的                  谁能接
===========  ========================  ============================
1            ``person:张三``            只有张三（教师指定 / 课程路由命中）
2            ``department:化学室``      该组任一管理员（先接先得）
3            ``all``                    全院任一管理员（滴滴式抢单）
===========  ========================  ============================

第 2 层的 ``department`` 是**「组」**，不限于教研室：教研室、科研组、平台
实验室都是组，组的类型存在 ``work_group.kind`` 里，只影响显示，不影响判定
——权限只认「我在不在这个组」，不认这个组叫什么类型。

本模块只回答「谁能看、谁能接、谁能办、谁能退、退到哪」，不碰数据库、
不认识 SQL。

判定只有一条总纲：**权限由「当前归属」决定，不由历史决定。**

每一层归属就是一个成员集合，动作全部从集合里派生（``my_groups`` 是这个人
所属的全部组，不是单个科室）：

============  =====================  ====  ====  ========  ====
当前归属       成员集合               可见   接单   受理/审批   退回
============  =====================  ====  ====  ========  ====
person:张三    {张三}                 张三   —     张三        张三
department:X  X 的全体管理员          全组   任一人  任一人       任一人
all           全院管理员              全院   任一人  任一人       任一人
============  =====================  ====  ====  ========  ====

（可见一列对超管一律放行，超管是兜底角色，不属于「其他人」；审批**不**放行。）

## 两种「退回」，两个主体，方向相反

**管理员退回 = 退单要申请人改。** 管理员手上没料，正确动作是发起调配（调拨/
平账），单还在他名下——料的问题用料的办法解决。所以退回只对应一种情况：
这张单本身有问题（数量不对、瓶选错、用途不明、课程挂错），必须回到申请人
那里改。落点因此只有一个：**申请人**。

**申请人退回 = 把单放给更多人办。** 指定给某人的单，如果那个人一直不批，
申请人不能一直等着。他可以把单从「某人」放回「某个组」，也没人接就再放回
「全院」。这个动作才是「转给别人」——单没变、料没变，只是收件人从一个人
变成一群人。

一句话记住：**管理员退 = 单有问题；申请人退 = 人不在；调 = 料不够。**
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable, Optional, Union

#: 归属标的：到人 / 到组 / 到全院
SCOPE_PERSON = "person"
SCOPE_DEPARTMENT = "department"
SCOPE_ALL = "all"

#: 组成员集合的两种写法：单个组名（老调用点）或组名集合（一个人可属多组）
GroupSet = Union[str, Iterable[str], None]

#: 认领失败的原因。三种原因要分开提示，别混成一句「操作失败」：
#: 用户看到的应当是「这单被谁拿走了」，不是一个红叉。
CLAIM_TAKEN = "taken"                      # 已经被别人接走
CLAIM_OTHER_DEPARTMENT = "other_department"  # 归别的组
CLAIM_ASSIGNED = "assigned"                # 本来就指定了某人
CLAIM_NOT_ALLOWED = "not_allowed"          # 不是管理员 / 状态不允许

#: 退回/放宽被拒的原因
RETURN_NOT_MEMBER = "not_member"           # 不在当前归属的成员集合里
RETURN_INVALID_STATE = "invalid_state"     # 单已经不在办（已办结/已关闭）
RETURN_NOT_REQUESTER = "not_requester"     # 不是申请人，不能把单放给别人
RETURN_ROOT = "root"                       # 已经在全院池，退无可退

#: 受理/审批被拒
ACT_NOT_MEMBER = "not_member"              # 不在当前归属的成员集合里


def _as_groups(groups: GroupSet) -> FrozenSet[str]:
    """归一成组名集合。

    ``str`` 是老调用点的写法（``department_of()`` 只返回一个科室），必须继续
    认；空串归一成空集合——**空值不能命中任何组**，否则一张组池的单会跑进
    所有没登记科室的人的待办里。
    """
    if groups is None:
        return frozenset()
    if isinstance(groups, str):
        key = groups.strip()
        return frozenset([key]) if key else frozenset()
    return frozenset(
        str(item).strip() for item in groups if str(item or "").strip()
    )


class AssignmentError(ValueError):
    """归属值非法（构造期错误，不是业务冲突）。"""


class ClaimError(Exception):
    """接单失败。``reason`` 是上面四个常量之一，页面按它给不同提示。"""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class ReturnError(Exception):
    """退回修改失败。"""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Assignment:
    """一张单的受理归属。

    ``key`` 在 ``person`` 下是人名、在 ``department`` 下是教研室名、
    在 ``all`` 下为空。之所以用「一个 scope 加一个 key」而不是三列，是因为
    ``custodian_route`` 表本身就是 ``(scope_type, scope_key)``——路由规则的
    形状与归属的形状一致，对接时不用翻译。
    """

    scope: str = SCOPE_ALL
    key: str = ""

    def __post_init__(self) -> None:
        scope = (self.scope or "").strip().lower()
        key = (self.key or "").strip()
        # 脏数据（老库空值、手改的库）一律按 all 处理，不在读路径上抛异常：
        # 一条错误的归属不该把整个待办页带崩。这也是老数据的兼容口径——
        # 历史上这些单本来就人人可见，不前向收窄。
        if scope not in (SCOPE_PERSON, SCOPE_DEPARTMENT, SCOPE_ALL):
            scope, key = SCOPE_ALL, ""
        if scope in (SCOPE_PERSON, SCOPE_DEPARTMENT) and not key:
            scope, key = SCOPE_ALL, ""
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "key", key)

    # ---------------------------------------------------------------- 构造
    @classmethod
    def of(cls, scope: str, key: str = "") -> "Assignment":
        return cls(scope=scope, key=key)

    @classmethod
    def person(cls, name: str) -> "Assignment":
        return cls(SCOPE_PERSON, name)

    @classmethod
    def department(cls, name: str) -> "Assignment":
        return cls(SCOPE_DEPARTMENT, name)

    @classmethod
    def everywhere(cls) -> "Assignment":
        return cls(SCOPE_ALL, "")

    # ---------------------------------------------------------------- 判定
    @property
    def is_person(self) -> bool:
        return self.scope == SCOPE_PERSON

    @property
    def is_department(self) -> bool:
        return self.scope == SCOPE_DEPARTMENT

    @property
    def is_all(self) -> bool:
        return self.scope == SCOPE_ALL

    @property
    def is_pool(self) -> bool:
        """还在池里（没到人）。这类单不能抽卡——没有「某人名下」。"""
        return not self.is_person

    def matches(self, scope: str, key: str = "") -> bool:
        """与库里那一行是否同一归属（CAS 条件用）。"""
        return self.scope == (scope or "").strip().lower() and self.key == (key or "").strip()

    def visible_to(self, me: str, my_groups: GroupSet = "") -> bool:
        """我的待办里该不该出现这张单。"""
        if self.is_all:
            return True
        if self.is_person:
            return self.key == (me or "").strip()
        return self.key in _as_groups(my_groups)

    def can_claim(
        self, me: str, my_groups: GroupSet = "", is_super_admin: bool = False
    ) -> bool:
        """能不能点「接单」。

        ``person`` 的单永远不能「接」——它已经有主了，包括指定给我的那种：
        那张单本来就该我办，不需要先认领一次。超管也不能抢别人名下的单，
        他要动单只能走申请人退回（放宽）或改派这两个显式动作。
        """
        if self.is_person:
            return False
        if is_super_admin or self.is_all:
            return True
        return self.key in _as_groups(my_groups)

    def can_handle(
        self,
        me: str,
        my_groups: GroupSet = "",
        is_admin: bool = False,
        is_super_admin: bool = False,
    ) -> bool:
        """能不能办这张单的业务动作（受理、审批、发料、兑付）。

        与「接单」的分工：接单是**声明负责**（收窄归属），受理是**把事做掉**。
        组池里的单两件事都能做——先接后办、直接办都行，谁办的谁的签名进流水。

        ``person`` 层超管也不代办：审批要留痕，代签等于把「谁批的」写错。
        超管要动这类单，只能走「退回/改派」这两个显式动作，改完归属再由成员
        本人办。
        """
        me = (me or "").strip()
        if self.is_person:
            return self.key == me
        if self.is_department:
            return bool(is_admin) and self.key in _as_groups(my_groups)
        return bool(is_admin)

    def can_return(
        self,
        me: str,
        my_groups: GroupSet = "",
        is_admin: bool = False,
        is_super_admin: bool = False,
    ) -> bool:
        """能不能把这张单退回去要申请人改（**管理员侧的动作**）。

        与 :meth:`can_handle` 同一套成员集合——**能办的人才能退**，因为「这单
        有问题」是个专业判断，得先看懂才说得出来。组池里的单本组任一人可退，
        全院池的任一管理员可退。超管兜底（申请人账号停用、经办人离职）。

        注意这里没有「退给上一级」这回事：落点恒为申请人，见
        :meth:`returned_to`。申请人那边的「放给更多人办」是另一个方法：
        :meth:`can_escalate`。
        """
        me = (me or "").strip()
        if is_super_admin:
            return True
        return self.can_handle(me, my_groups, is_admin=is_admin, is_super_admin=False)

    def returned_to(self, requester: str) -> "Assignment":
        """退回之后的归属：**申请人**，不是任何池。

        单回到申请人手上，他改数量、换瓶、补用途，改完重新提交时归属重算。
        落在池里没有意义：池子里的单本来就没到人手上，再退一次只是原地打转，
        而问题还留在单据里。
        """
        requester = (requester or "").strip()
        return Assignment.person(requester) if requester else Assignment.everywhere()

    # ---------------------------------------------------------------- 申请人侧
    def can_escalate(
        self, me: str, requester: str = "", is_super_admin: bool = False
    ) -> bool:
        """能不能把这张单**放给更多人办**（申请人侧的动作）。

        只有申请人本人（或超管兜底）能放。管理员不能替申请人放——「这单该
        给全组看还是全院看」是申请人对自己那张单的决定权，别人替他放等于替
        他放弃「指定某人」这个承诺。

        已经在 ``all`` 的没有可放的，见 :meth:`escalated_to`。
        """
        if self.is_all:
            return False
        me = (me or "").strip()
        if is_super_admin:
            return True
        requester = (requester or "").strip()
        return bool(requester) and me == requester

    def escalated_to(
        self, my_groups: GroupSet = "", target_group: str = ""
    ) -> Optional["Assignment"]:
        """放给更多人时落到哪。``None`` 表示已经在全院池，放无可放。

        - ``person`` → 组：优先用调用方指定的那个组（申请人可能属于教研室和
          科研组两个组，退给哪个由他选）；没指定就取他的第一个组。一个组都
          没有的人只能直接放回全院池。
        - ``department`` → ``all``。
        """
        if self.is_all:
            return None
        target_group = (target_group or "").strip()
        if self.is_person:
            if target_group:
                return Assignment.department(target_group)
            groups = sorted(_as_groups(my_groups))
            return Assignment.department(groups[0]) if groups else Assignment.everywhere()
        return Assignment.everywhere()

    def can_transfer(self, me: str, requester: str = "", is_super_admin: bool = False) -> bool:
        """能不能改派（把单点名叫别人 / 别的组办）。

        三种人：当前的持有人（``person`` 层本人）、申请人、超管。

        申请人也在内，是因为「指定的人不批」的出口之一就是改派到另一个组或
        另一个人；如果只有持有人能改派，持有人不动，申请人就永远卡住——那正
        是他要解决的问题。
        """
        me = (me or "").strip()
        if is_super_admin:
            return True
        if self.is_person and self.key == me:
            return True
        return bool(requester) and me == (requester or "").strip()

    def can_transfer_to(self, target: "Assignment") -> bool:
        """改派目标合不合理。

        不能改派到自己（原地踏步），也不能把单改派给「全院池」——那是放宽，
        走 :meth:`can_escalate` 那条路，两条路混起来会让台账分不清「换人办」
        和「没人接」。
        """
        return (
            not target.is_all
            and not (target.scope == self.scope and target.key == self.key)
        )

    def handle_blocked_message(self) -> str:
        """办不了时的提示语（要说清楚该找谁）。"""
        if self.is_person:
            return f"这张单指定由 {self.key} 受理，其他人不能办理"
        if self.is_department:
            return f"这张单归 {self.key}，只有该组的管理员可以办理"
        return "只有管理员可以办理单据"

    def describe(self) -> str:
        if self.is_person:
            return f"指定由 {self.key} 受理"
        if self.is_department:
            return f"归 {self.key}（该组任一管理员可接可办）"
        return "全院池（任一管理员可接可办）"

    def __str__(self) -> str:  # pragma: no cover - 便于调试
        return f"{self.scope}:{self.key}" if self.key else self.scope


def assignment_of(row: dict) -> Assignment:
    """从一行单据（dict / sqlite3.Row）读出归属，空值按 all。"""
    if not row:
        return Assignment.everywhere()
    getter = row.get if hasattr(row, "get") else lambda k, d=None: row[k]
    return Assignment(
        scope=getter("custodian_scope") or "",
        key=getter("custodian_key") or "",
    )


def claimed_from_of(row: dict) -> Optional[Assignment]:
    """读「认领前的归属」。

    目前**没有业务读者**：退回不再按来源还原，落点恒为申请人。留着它是因为
    这五列是历史事实（这单当初从哪个池被人接走），排查「谁把全院池的单收成
    自己的」时要看它。
    """
    if not row:
        return None
    getter = row.get if hasattr(row, "get") else lambda k, d=None: row[k]
    scope = (getter("claimed_from_scope") or "").strip()
    if not scope:
        return None
    return Assignment(scope=scope, key=getter("claimed_from_key") or "")


__all__ = [
    "SCOPE_PERSON",
    "SCOPE_DEPARTMENT",
    "SCOPE_ALL",
    "CLAIM_TAKEN",
    "CLAIM_OTHER_DEPARTMENT",
    "CLAIM_ASSIGNED",
    "CLAIM_NOT_ALLOWED",
    "RETURN_NOT_MEMBER",
    "RETURN_INVALID_STATE",
    "RETURN_NOT_REQUESTER",
    "RETURN_ROOT",
    "ACT_NOT_MEMBER",
    "AssignmentError",
    "ClaimError",
    "ReturnError",
    "Assignment",
    "assignment_of",
    "claimed_from_of",
]
