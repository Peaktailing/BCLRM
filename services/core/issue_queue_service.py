"""待办队列与单据归属的数据访问。

两张单（零星/课程领用工单、配方需求单）在 ``v_issue_queue`` 里被投影成
同一形状，归属五列也在这两张表上同名同义。**跨表读写放在 services 层，
判定留在 business 层**——业务层不该拼 SQL，数据层也不该决定「谁能接」。

这里刻意不做任何权限判断：``claim`` 只负责「按读到的旧状态做条件更新」，
`rowcount=0` 就是结果。谁能接、谁能退，全部在上层用
:mod:`domain.assignment` 判完再来。
"""
from __future__ import annotations

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
        my_department: str = "",
        is_super_admin: bool = False,
        kinds: Optional[Iterable[str]] = None,
        limit: int = 300,
    ) -> List[Dict[str, Any]]:
        """在办单，按提交时间升序（先来的先办）。

        过滤是三条 OR：指定给我 / 归我教研室 / 全院池。空归属也必须算进来
        ——老数据两列都是空的，只写 ``= 'all'`` 会让所有在办的历史单从待办
        里消失，那不是收窄，是丢失。
        """
        clauses = [OPEN_CONDITION]
        params: list[Any] = []

        if not is_super_admin:
            department = (my_department or "").strip()
            visibility = "(custodian_scope = 'person' AND custodian_key = ?)"
            params.append(me)
            if department:
                visibility += " OR (custodian_scope = 'department' AND custodian_key = ?)"
                params.append(department)
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

    def release(
        self, kind: str, ref: str, scope: str, key: str, from_key: str
    ) -> int:
        table, column = self._table(kind)
        return self.db.execute_update(
            f"UPDATE {table} SET custodian_scope = ?, custodian_key = ?, "
            "claimed_at = NULL, claimed_from_scope = '', claimed_from_key = '' "
            f"WHERE {column} = ? AND COALESCE(custodian_scope, '') = 'person' "
            "AND COALESCE(custodian_key, '') = ?",
            (scope, key, ref, from_key),
        )

    def transfer(self, kind: str, ref: str, target: str, from_key: str) -> int:
        table, column = self._table(kind)
        return self.db.execute_update(
            f"UPDATE {table} SET custodian_key = ? WHERE {column} = ? "
            "AND COALESCE(custodian_scope, '') = 'person' "
            "AND COALESCE(custodian_key, '') = ?",
            (target, ref, from_key),
        )

    # ---------------------------------------------------------------- 内部
    @staticmethod
    def _table(kind: str):
        if kind not in TABLES:
            raise ValueError(f"未知的单据类型：{kind}")
        return TABLES[kind]


issue_queue_service = IssueQueueService()

__all__ = [
    "IssueQueueService",
    "issue_queue_service",
    "KIND_ORDER",
    "KIND_REQUIREMENT",
    "TABLES",
    "OPEN_CONDITION",
]
