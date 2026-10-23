"""保管人路由表：谁受理哪门课 / 哪个项目 / 哪个科室的申请。

BCLRM 原来没有这张映射——``experiment_course`` 只有 ``teacher``，没有
``custodian``。于是教师申领时系统只能按「本人 → 本教研室 → 全院」去
全院撮合，跳过「这门课归谁管」这一层。后果不是效率问题，而是责任问题：
受理管理员全程不知情，也不会去补料。

本模块只做存取，不判断优先级——优先级（先课程、再科室、最后兜底）由
中台的 ``CompositeRouter`` 决定，那是策略，会变。
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from db.database import db
from domain.custody import Custodian
from utils.error_handler import logger
from utils.field_mapper import CustodianRouteField

# 匹配维度
SCOPE_COURSE = "course"
SCOPE_PROJECT = "project"
SCOPE_DEPARTMENT = "department"
SCOPE_PERSON = "person"

SCOPE_LABELS = {
    SCOPE_COURSE: "课程",
    SCOPE_PROJECT: "科研项目",
    SCOPE_DEPARTMENT: "科室",
    SCOPE_PERSON: "个人",
}


class CustodianRouteRepository:
    """``custodian_route`` 表的存取。"""

    def __init__(self, database=None) -> None:
        self.db = database or db

    # ---------------------------------------------------------------- 读
    def rows(self, scope_type: Optional[str] = None) -> list[dict]:
        """读规则。

        表不存在时返回空并留日志，而不是把整个页面带崩：升级到含本表的
        版本后若忘了重启，表现应该是「还没配路由」，不是「系统坏了」。
        ``init_tables()`` 是幂等的，重启一次就自动补齐。
        """
        try:
            if scope_type:
                return self.db.execute_query(
                    "SELECT * FROM custodian_route WHERE scope_type = ? "
                    "ORDER BY priority, scope_key",
                    (scope_type,),
                )
            return self.db.execute_query(
                "SELECT * FROM custodian_route ORDER BY scope_type, priority, scope_key"
            )
        except Exception as exc:
            logger.warning(f"读取保管人路由失败（custodian_route 可能尚未创建，重启应用即可）: {exc}")
            return []

    def table_ready(self) -> bool:
        """路由表是否已建（页面用来区分「没配」和「没建表」）。"""
        try:
            self.db.execute_query("SELECT 1 FROM custodian_route LIMIT 1")
            return True
        except Exception:
            return False

    def rules(self, scope_type: str, department_of=None) -> dict[str, Custodian]:
        """某个维度的规则：``scope_key → Custodian``。

        ``department_of`` 用来补齐保管人的科室（第二段撮合的"同科室优先"
        依赖它）。传 ``None`` 时科室留空，撮合会退化为纯全院顺序。
        """
        mapping: dict[str, Custodian] = {}
        for row in self.rows(scope_type):
            key = (row.get(CustodianRouteField.SCOPE_KEY) or "").strip()
            name = (row.get(CustodianRouteField.CUSTODIAN) or "").strip()
            if not name:
                continue
            department = department_of(name) if department_of else ""
            mapping[key] = Custodian(name=name, department=department or "")
        return mapping

    def custodian_names(self) -> tuple[str, ...]:
        """表里出现过的受理管理员（页面下拉用）。"""
        names: list[str] = []
        for row in self.db.execute_query(
            "SELECT DISTINCT custodian FROM custodian_route ORDER BY custodian"
        ):
            name = (row.get("custodian") or "").strip()
            if name and name not in names:
                names.append(name)
        return tuple(names)

    # ---------------------------------------------------------------- 写
    def upsert(
        self,
        scope_type: str,
        scope_key: str,
        custodian: str,
        priority: int = 100,
        remark: str = "",
    ) -> int:
        """配置一条规则（同维度同键覆盖，不新增重复行）。"""
        if scope_type not in SCOPE_LABELS:
            raise ValueError(f"未知的匹配维度：{scope_type}")
        if not (custodian or "").strip():
            raise ValueError("受理管理员不能为空")
        scope_key = (scope_key or "").strip()

        existing = self.db.execute_query(
            "SELECT id FROM custodian_route WHERE scope_type = ? AND scope_key = ?",
            (scope_type, scope_key),
        )
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if existing:
            route_id = int(existing[0]["id"])
            self.db.execute_update(
                "UPDATE custodian_route SET custodian = ?, priority = ?, remark = ?, "
                "updated_at = ? WHERE id = ?",
                (custodian.strip(), int(priority), remark, now, route_id),
            )
            return route_id
        return self.db.execute_insert(
            "INSERT INTO custodian_route (scope_type, scope_key, custodian, priority, remark) "
            "VALUES (?, ?, ?, ?, ?)",
            (scope_type, scope_key, custodian.strip(), int(priority), remark),
        )

    def delete(self, route_id: int) -> bool:
        return self.db.execute_update(
            "DELETE FROM custodian_route WHERE id = ?", (int(route_id),)
        ) > 0

    def delete_by_scope(self, scope_type: str, scope_key: str) -> bool:
        return self.db.execute_update(
            "DELETE FROM custodian_route WHERE scope_type = ? AND scope_key = ?",
            (scope_type, (scope_key or "").strip()),
        ) > 0

    def seed_from_courses(self, rows: Iterable[dict], custodian: str) -> int:
        """批量把一批课程指给同一个管理员（开学前的初始化用）。

        ``rows`` 每项含 ``course_name`` 与可选 ``class_name``。有班级时按
        「课程/班级」建精确键，否则退到课程级。
        """
        count = 0
        for row in rows:
            course = (row.get("course_name") or row.get("course") or "").strip()
            if not course:
                continue
            klass = (row.get("class_name") or row.get("class") or "").strip()
            key = f"{course}/{klass}" if klass else course
            self.upsert(SCOPE_COURSE, key, custodian)
            count += 1
        return count


custodian_route_repository = CustodianRouteRepository()


__all__ = [
    "CustodianRouteRepository",
    "custodian_route_repository",
    "SCOPE_COURSE",
    "SCOPE_PROJECT",
    "SCOPE_DEPARTMENT",
    "SCOPE_PERSON",
    "SCOPE_LABELS",
]
