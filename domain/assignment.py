"""单据归属：这一张单该谁受理。

BCLRM 原来只有一条「全院都能看见、谁点谁办」的隐含规则。真实业务里工单
本来就有主：每门课对应一个管理员，教研室里的申请也往往指定提交人。于是
「抢单」不是主问题，**「归属算不算得出来、算不出来往哪落」**才是。

三层降级，每一层都是明确配置，不存在猜：

===========  ====================  ================================
层级          归属标的               谁能接
===========  ====================  ================================
1            ``person:张三``        只有张三（教师指定 / 课程路由命中）
2            ``department:化学室``  该教研室任一管理员（先接先得）
3            ``all``                全院任一管理员（滴滴式抢单）
===========  ====================  ================================

本模块只回答「谁能看、谁能接、谁能退、退回落到哪」，不碰数据库、不认识
SQL。判定之所以要独立成领域逻辑，是因为它有一条容易被写散的不变量：

    **同教研室的其他管理员没有退回权。**

认领是一条单向收窄（组 → 人）。如果同室旁人能把它改回去，认领就退化成
一个可被第三方撤回的临时状态，抢单只是从「接单」挪到了「退回」按钮上。
可见性解决「不漏单」，可改性解决「谁负责」——两件事不能共用一条规则。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: 归属标的：到人 / 到组 / 到全院
SCOPE_PERSON = "person"
SCOPE_DEPARTMENT = "department"
SCOPE_ALL = "all"

#: 认领失败的原因。三种原因要分开提示，别混成一句「操作失败」：
#: 用户看到的应当是「这单被谁拿走了」，不是一个红叉。
CLAIM_TAKEN = "taken"                      # 已经被别人接走
CLAIM_OTHER_DEPARTMENT = "other_department"  # 归别的教研室
CLAIM_ASSIGNED = "assigned"                # 本来就指定了某人
CLAIM_NOT_ALLOWED = "not_allowed"          # 不是管理员 / 状态不允许

#: 退回被拒的原因
RELEASE_NOT_OWNER = "not_owner"            # 不是当前接单人，也不是超管
RELEASE_NOT_PERSON = "not_person"          # 不在个人名下，没有「退」这个动作
RELEASE_ROOT = "root"                      # 已经落在 all，退无可退


class AssignmentError(ValueError):
    """归属值非法（构造期错误，不是业务冲突）。"""


class ClaimError(Exception):
    """接单失败。``reason`` 是上面四个常量之一，页面按它给不同提示。"""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class ReleaseError(Exception):
    """退回失败。"""

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

    def visible_to(self, me: str, my_department: str = "") -> bool:
        """我的待办里该不该出现这张单。"""
        if self.is_all:
            return True
        if self.is_person:
            return self.key == (me or "").strip()
        return bool(my_department) and self.key == my_department.strip()

    def can_claim(
        self, me: str, my_department: str = "", is_super_admin: bool = False
    ) -> bool:
        """能不能点「接单」。

        ``person`` 的单永远不能「接」——它已经有主了，包括指定给我的那种：
        那张单本来就该我办，不需要先认领一次。超管也不能抢别人名下的单，
        他要动单只能走「退回」或「转交」这两个显式动作。
        """
        if self.is_person:
            return False
        if is_super_admin or self.is_all:
            return True
        return bool(my_department) and self.key == my_department.strip()

    def can_release(self, me: str, is_super_admin: bool = False) -> bool:
        """能不能把这张单退回池。

        **同教研室的其他管理员不算。** 组内可见是为了不漏单，不代表组内
        互相可以改单据归属。唯一的例外是超管：真人离职、账号停用时，只有
        他能替当事人把单放回去。
        """
        if self.is_all:
            return False
        if self.is_person:
            return self.key == (me or "").strip() or is_super_admin
        return is_super_admin

    def can_transfer(self, me: str, is_super_admin: bool = False) -> bool:
        """能不能把这张单转给别人（与退回同一套权限）。"""
        return self.is_person and (
            self.key == (me or "").strip() or is_super_admin
        )

    def after_release(
        self,
        my_department: str = "",
        claimed_from: Optional["Assignment"] = None,
    ) -> Optional["Assignment"]:
        """退回之后落到哪一级。``None`` 表示退无可退。

        原则只有一条：**退回只能放宽，不能顺手收窄。**

        - 认领来的单（有 ``claimed_from``）：恢复原处。原来在全院池，退回
          还回全院池，不能因为接单人有教研室就降成「他的教研室」。
        - 指定来的单（没有 ``claimed_from``）：降到下一级。指定给某人 → 本
          教研室（没有教研室就全院）；教研室 → 全院。
        """
        if self.is_all:
            return None
        if claimed_from is not None and not claimed_from.is_person:
            return claimed_from
        if self.is_person:
            department = (my_department or "").strip()
            return Assignment.department(department) if department else Assignment.everywhere()
        return Assignment.everywhere()

    def describe(self) -> str:
        if self.is_person:
            return f"指定由 {self.key} 受理"
        if self.is_department:
            return f"归 {self.key}（任一管理员可接）"
        return "全院池（任一管理员可接）"

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
    """读「认领前的归属」。没有就是 ``None``（指定来的单）。"""
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
    "RELEASE_NOT_OWNER",
    "RELEASE_NOT_PERSON",
    "RELEASE_ROOT",
    "AssignmentError",
    "ClaimError",
    "ReleaseError",
    "Assignment",
    "assignment_of",
    "claimed_from_of",
]
