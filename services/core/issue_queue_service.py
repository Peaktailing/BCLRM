"""待办队列与单据归属的数据访问。

两张单（零星/课程领用工单、配方需求单）在 ``v_issue_queue`` 里被投影成
同一形状，归属五列也在这两张表上同名同义。**跨表读写放在 services 层，
判定留在 business 层**——业务层不该拼 SQL，数据层也不该决定「谁能接」。

这里刻意不做任何权限判断：``claim`` 只负责「按读到的旧状态做条件更新」，
`rowcount=0` 就是结果。谁能接、谁能退，全部在上层用
:mod:`domain.assignment` 判完再来。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from db.database import db
from utils.error_handler import logger

KIND_ORDER = "order"
KIND_REQUIREMENT = "requirement"

TABLES = {
    KIND_ORDER: ("borrow_order", "order_number"),
    KIND_REQUIREMENT: ("requirement_sheet", "sheet_number"),
}

#: 「这张单还需要人处理」的口径。两类单的状态字段语义不同（工单是中文
#: 审批状态，需求单是英文流转状态），只能分开写；写在视图里会把「在办」
#: 的定义固化到 schema，改一次就要重建视图。
OPEN_CONDITION = (
    "((kind = 'order' AND approval_status = '待审批' AND status = '待审批')"
    " OR (kind = 'requirement' AND status IN ('submitted', 'partial')))"
)


class IssueQueueService:
    """``v_issue_queue`` 与归属列的读写。"""

    def __init__(self, database=None) -> None:
        self.db = database or db

    # ---------------------------------------------------------------- 读
    def row(self, kind: str, ref: str) -> Optional[Dict[str, Any]]:
        table, column = self._table(kind)
        rows = self.db.execute_query(f"SELECT * FROM {table} WHERE {column} = ?", (ref,))
        return rows[0] if rows else None

    def open_rows(
        self,
        me: str,
        my_groups: Any = "",
        is_super_admin: bool = False,
        kinds: Optional[Iterable[str]] = None,
        limit: int = 300,
    ) -> List[Dict[str, Any]]:
        """在办单，按提交时间升序（先来的先办）。

        过滤是三条 OR：指定给我 / 归我所在的某个组 / 全院池。空归属也必须算
        进来——老数据两列都是空的，只写 ``= 'all'`` 会让所有在办的历史单从待
        办里消失，那不是收窄，是丢失。

        ``my_groups`` 可以是一个组名，也可以是这个人所属的全部组：一个人可能
        同时在教研室和科研组，两个组池的单都该进他的待办。空集合不命中任何
        组——空字符串当组名会让一张组池的单跑进所有没登记组的人那里。
        """
        clauses = [OPEN_CONDITION]
        params: list[Any] = []

        if not is_super_admin:
            groups = [g for g in _group_list(my_groups) if g]
            visibility = "(custodian_scope = 'person' AND custodian_key = ?)"
            params.append(me)
            if groups:
                visibility += (
                    " OR (custodian_scope = 'department' AND custodian_key IN ("
                    + ", ".join("?" for _ in groups)
                    + "))"
                )
                params.extend(groups)
            visibility += (
                " OR custodian_scope = 'all'"
                " OR custodian_scope IS NULL OR custodian_scope = ''"
            )
            clauses.append(f"({visibility})")

        if kinds:
            kinds = tuple(kinds)
            clauses.append("kind IN (" + ", ".join("?" for _ in kinds) + ")")
            params.extend(kinds)

        sql = (
            "SELECT * FROM v_issue_queue WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at ASC, ref ASC LIMIT ?"
        )
        params.append(int(limit))
        try:
            return self.db.execute_query(sql, tuple(params))
        except Exception as exc:
            # 视图没建（升级后没重启）不该白屏：空队列 + 一条日志。
            logger.warning(f"读取待办队列失败（v_issue_queue 可能尚未创建）: {exc}")
            return []

    def open_sheets_of_requester(
        self, requester: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """这个人提交的、还在办的需求单。

        走 ``requirement_sheet`` 而不是 ``v_issue_queue``：待办视图按**收件人**
        过滤，申请人自己常常不在收件人里（单已经指定给别人了），从视图里查会
        得到「我的单不见了」——而这条列表的用途恰恰是让他把单放给别人。
        """
        requester = (requester or "").strip()
        if not requester:
            return []
        return self.db.execute_query(
            "SELECT * FROM requirement_sheet WHERE requester = ? "
            "AND COALESCE(status, '') IN ('submitted', 'partial') "
            "ORDER BY created_at DESC LIMIT ?",
            (requester, int(limit)),
        )

    # ---------------------------------------------------------------- 写
    def set_assignment(self, kind: str, ref: str, scope: str, key: str) -> int:
        table, column = self._table(kind)
        return self.db.execute_update(
            f"UPDATE {table} SET custodian_scope = ?, custodian_key = ? WHERE {column} = ?",
            (scope, key, ref),
        )

    def claim(
        self,
        kind: str,
        ref: str,
        me: str,
        from_scope: str,
        from_key: str,
        now: str,
    ) -> int:
        """条件更新：把归属从组/池收窄到人。

        条件里带的是**读到的那个状态的字面量**，不是 ``custodian_scope``
        自引用——这样 ``rowcount=0`` 的含义是确定的「我看到的已经被改过」，
        而不是「可能被改过也可能 SQL 写错了」。
        """
        table, column = self._table(kind)
        return self.db.execute_update(
            f"UPDATE {table} SET custodian_scope = 'person', custodian_key = ?, "
            "claimed_at = ?, claimed_from_scope = ?, claimed_from_key = ? "
            f"WHERE {column} = ? AND COALESCE(custodian_scope, '') = ? "
            "AND COALESCE(custodian_key, '') = ?",
            (me, now, from_scope, from_key, ref, from_scope, from_key),
        )

    def return_to_requester(
        self,
        kind: str,
        ref: str,
        requester: str,
        reason: str,
        from_scope: str,
        from_key: str,
    ) -> int:
        """退回修改：归属回到申请人手上，单随即离开待办。

        两张表的状态字段语义不同，只能分开写：

        - 工单：复用「已驳回」。驳回本来就是「这张单不能就这么过」，申请人
          改完重新提一张；额外带 ``approval_status = '待审批'`` 做原子抢占，
          已经批过的单不会被退回踩平。
        - 需求单：置 ``returned``，并把原因写进 ``return_reason``。它不在
          在办状态里，所以退回后自动退出待办与保底累计。

        条件里带的是**读到的旧状态字面量**（scope + key），组池被人抢先认领
        时 `rowcount=0`，不会把别人手上的单退走。
        """
        table, column = self._table(kind)
        if kind == KIND_ORDER:
            return self.db.execute_update(
                f"UPDATE {table} SET custodian_scope = 'person', custodian_key = ?, "
                "claimed_at = NULL, status = '已驳回', approval_status = '已驳回', "
                "approval_remark = ?, approval_time = ? "
                f"WHERE {column} = ? AND COALESCE(custodian_scope, '') = ? "
                "AND COALESCE(custodian_key, '') = ? AND approval_status = '待审批'",
                (
                    requester,
                    reason,
                    _now(),
                    ref,
                    from_scope,
                    from_key,
                ),
            )
        return self.db.execute_update(
            f"UPDATE {table} SET custodian_scope = 'person', custodian_key = ?, "
            "claimed_at = NULL, status = 'returned', return_reason = ? "
            f"WHERE {column} = ? AND COALESCE(custodian_scope, '') = ? "
            "AND COALESCE(custodian_key, '') = ? AND status IN ('submitted', 'partial')",
            (requester, reason, ref, from_scope, from_key),
        )

    def escalate(
        self,
        kind: str,
        ref: str,
        scope: str,
        key: str,
        from_scope: str,
        from_key: str,
    ) -> int:
        """放宽归属（申请人侧）：``person`` → 组、组 → 全院。

        与 :meth:`return_to_requester` 的方向**相反**：退回是「单要改」，单
        离开在办；放宽是「人不在」，单还在办，只是收件人从一个人变成一群人。
        所以这里**一个字都不碰状态字段**——单据的业务状态不因为换了人办而改变。
        """
        return self.move(kind, ref, scope, key, from_scope, from_key)

    def transfer(
        self,
        kind: str,
        ref: str,
        scope: str,
        key: str,
        from_scope: str,
        from_key: str,
    ) -> int:
        """改派：换成另一个**具体**的受理方（人，或另一个组）。

        与 :meth:`escalate` 的差别只是目标谁说了算：放宽的目标是「上一级」，
        改派的目标由操作人挑。SQL 一样，语义不同，所以分成两个入口——将来
        其中一个要加条件（比如改派要求目标必须是管理员）时不会互相牵连。
        """
        return self.move(kind, ref, scope, key, from_scope, from_key)

    def move(
        self,
        kind: str,
        ref: str,
        scope: str,
        key: str,
        from_scope: str,
        from_key: str,
    ) -> int:
        """换收件人（不改业务状态）。

        条件带读到的旧 scope + key 两个字面量：组池的单被人抢先认领时
        `rowcount=0`，不会把别人手上的单又推走。``claimed_at`` 一并清掉——它
        记的是「这张单被人认领过」，换了收件人之后那件事已经跟当前状态无关了。
        """
        table, column = self._table(kind)
        return self.db.execute_update(
            f"UPDATE {table} SET custodian_scope = ?, custodian_key = ?, "
            "claimed_at = NULL, claimed_from_scope = '', claimed_from_key = '' "
            f"WHERE {column} = ? AND COALESCE(custodian_scope, '') = ? "
            "AND COALESCE(custodian_key, '') = ?",
            (scope, key, ref, from_scope, from_key),
        )

    # ---------------------------------------------------------------- 内部
    @staticmethod
    def _table(kind: str):
        if kind not in TABLES:
            raise ValueError(f"未知的单据类型：{kind}")
        return TABLES[kind]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _group_list(groups: Any) -> List[str]:
    """组名归一：单个字符串与集合都认，空值一律归一成空列表。"""
    if groups is None:
        return []
    if isinstance(groups, str):
        value = groups.strip()
        return [value] if value else []
    return [str(item).strip() for item in groups if str(item or "").strip()]


issue_queue_service = IssueQueueService()

__all__ = [
    "IssueQueueService",
    "issue_queue_service",
    "KIND_ORDER",
    "KIND_REQUIREMENT",
    "TABLES",
    "OPEN_CONDITION",
]
