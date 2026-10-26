"""管理组（教研室 / 科研组）与成员。

## 为什么不是 ``person.department`` 一列

一个人可能同时属于教研室和科研组，几个组之间还会交叉（同一门课的老师分散
在不同课题组）。一列文本装不下这种关系，能装下的只有「最后一填的那个」——
于是换一次组，所有人的待办跟着错一次。

所以组与人是多对多：``work_group`` 存组本身，``work_group_member`` 存成员。
``person.department`` 保留，但退化成**主组**：只在成员表查不到时兜底（升级
前的老数据、临时账号）。两处都查不到的，归属判定按「没有任何组」处理，而
不是按「空字符串等于所有组」——空值命中会让一张组池的单跑进所有人待办。

## kind 不参与权限

``kind`` 只有两个用途：显示（「来自化学教研室 / 来自某某课题组」）和筛选。
归属的粒度只有三级（人 / 组 / 全院），组是哪一种组是组织架构的属性，不是
权限的维度。把它塞进判定，明天加第三种组（教学中心、平台实验室）就要改
权限代码。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from db.database import db
from utils.error_handler import logger

#: 组类型。只影响显示与筛选，不参与权限判定。
GROUP_DEPARTMENT = "department"   # 教研室
GROUP_RESEARCH = "research"       # 科研组 / 课题组
GROUP_OTHER = "other"             # 其他（平台、中心）

GROUP_KIND_LABELS = {
    GROUP_DEPARTMENT: "教研室",
    GROUP_RESEARCH: "科研组",
    GROUP_OTHER: "其他",
}


class WorkGroupService:
    """组的读写。**不做权限判断**，只回答「谁在哪个组」。"""

    def __init__(self, database=None) -> None:
        self.db = database or db

    # ---------------------------------------------------------------- 读
    def groups_of(self, person_name: str) -> List[str]:
        """这个人属于哪些组。

        成员表优先；查不到才回落 ``person.department``（主组）。回落这一条是
        给升级前的老数据用的，不是给「懒得建组」用的——一旦某人有成员记录，
        主组就不再参与判定，避免「退组之后还能看见组里的单」。
        """
        name = (person_name or "").strip()
        if not name:
            return []
        try:
            rows = self.db.execute_query(
                "SELECT group_name FROM work_group_member WHERE person_name = ? "
                "ORDER BY group_name",
                (name,),
            )
        except Exception as exc:  # 表还没建（升级后没重启）
            logger.warning(f"查询组成员失败：{exc}")
            rows = []
        groups = [str(row["group_name"]).strip() for row in rows if row["group_name"]]
        if groups:
            return groups
        return [d for d in [self._primary_department(name)] if d]

    def members_of(self, group_name: str) -> List[str]:
        """组里有哪些人。"""
        group_name = (group_name or "").strip()
        if not group_name:
            return []
        rows = self.db.execute_query(
            "SELECT person_name FROM work_group_member WHERE group_name = ? "
            "ORDER BY person_name",
            (group_name,),
        )
        return [str(row["person_name"]).strip() for row in rows if row["person_name"]]

    def list_groups(
        self, kinds: Optional[Iterable[str]] = None, include_empty: bool = False
    ) -> List[Dict[str, Any]]:
        """全部组，带成员数。默认不列空组（下拉框里选一个没人接的组没有意义）。"""
        sql = (
            "SELECT g.name, g.kind, "
            "(SELECT COUNT(*) FROM work_group_member m WHERE m.group_name = g.name) AS member_count "
            "FROM work_group g"
        )
        params: list[Any] = []
        clauses: List[str] = []
        if kinds:
            kinds = tuple(kinds)
            clauses.append("g.kind IN (" + ", ".join("?" for _ in kinds) + ")")
            params.extend(kinds)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY g.kind, g.name"
        try:
            rows = self.db.execute_query(sql, tuple(params))
        except Exception as exc:
            logger.warning(f"读取管理组失败：{exc}")
            return []
        if include_empty:
            return rows
        return [row for row in rows if int(row.get("member_count") or 0) > 0]

    def kind_of(self, group_name: str) -> str:
        group_name = (group_name or "").strip()
        if not group_name:
            return ""
        rows = self.db.execute_query(
            "SELECT kind FROM work_group WHERE name = ?", (group_name,)
        )
        return (rows[0]["kind"] or "") if rows else ""

    def exists(self, group_name: str) -> bool:
        return bool(self.kind_of(group_name))

    def describe(self, group_name: str) -> str:
        """人话：``化学教研室`` → ``化学教研室（教研室）``。"""
        kind = self.kind_of(group_name)
        label = GROUP_KIND_LABELS.get(kind, "")
        return f"{group_name}（{label}）" if label else group_name

    def is_member(self, group_name: str, person_name: str) -> bool:
        return (group_name or "").strip() in self.groups_of(person_name)

    # ---------------------------------------------------------------- 写
    def add_group(self, name: str, kind: str = GROUP_DEPARTMENT, note: str = "") -> bool:
        name = (name or "").strip()
        if not name:
            return False
        # 已存在不是失败：``INSERT OR IGNORE`` 在这一列上是幂等的，调用方
        # （页面、回填脚本）不该为「加过一个同名的组」写分支。
        self.db.execute_insert(
            "INSERT OR IGNORE INTO work_group (name, kind, note) VALUES (?, ?, ?)",
            (name, kind or GROUP_DEPARTMENT, note or ""),
        )
        return True

    def add_member(self, group_name: str, person_name: str) -> bool:
        group_name = (group_name or "").strip()
        person_name = (person_name or "").strip()
        if not (group_name and person_name):
            return False
        self.db.execute_insert(
            "INSERT OR IGNORE INTO work_group_member (group_name, person_name) "
            "VALUES (?, ?)",
            (group_name, person_name),
        )
        return True

    def remove_member(self, group_name: str, person_name: str) -> int:
        return self.db.execute_update(
            "DELETE FROM work_group_member WHERE group_name = ? AND person_name = ?",
            ((group_name or "").strip(), (person_name or "").strip()),
        )

    # ---------------------------------------------------------------- 内部
    def _primary_department(self, name: str) -> str:
        rows = self.db.execute_query(
            "SELECT department FROM person WHERE name = ?", (name,)
        )
        if not rows:
            return ""
        return (rows[0]["department"] or "").strip()


work_group_service = WorkGroupService()

__all__ = [
    "WorkGroupService",
    "work_group_service",
    "GROUP_DEPARTMENT",
    "GROUP_RESEARCH",
    "GROUP_OTHER",
    "GROUP_KIND_LABELS",
]
