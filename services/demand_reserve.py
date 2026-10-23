"""保底：本学年该保管人还没兑现的需求量。

「他也够用」这个约束要落地，必须回答一个具体问题：**他名下这门课/这个
项目，今年还要用多少这种物质？** 这个问题有答案的前提是三条：

1. **一年一轮**。实验大多一年只做一次，所以量的周期是学年（9/1 起算），
   不是月、也不是无限期。跨学年的单不参与——去年的账不该压着今年的料。
2. **单上有来源**。``requirement_sheet.source_code`` 记着「课程/实验」
   或项目号，可以反查它归谁管。
3. **能算出还没发多少**。这一条分两层：

   - 单头层面，只认 ``submitted`` 与 ``partial``。``issued`` 是全部兑完，
     ``draft`` 是老师自己还没想好，两者都不占料。
   - 行层面，取 ``quantity − issued_quantity``。**这是关键**：整单置
     ``issued`` 会把没发出去的行一起吞掉，而按全量算又把已经发到手上的
     料当成欠量。逐行扣减是唯一同时对得上账、又不压料的口径。

算不出来时返回 None，表示**不锁料**。保底是优化，让一件事"宁可发不出"
比"多发了一点"危险得多：料没发出去，实验当堂停；料多抽了，下一节还能
补领。
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from capabilities.circulation.picking import ReserveQuery
from db.database import Database
from domain.academic_year import AcademicYear
from domain.substance import SubstanceRef
from domain.units import Quantity, parse_unit
from services.custodian_route import custodian_route_repository
from utils.error_handler import logger

#: 还占着料的状态。``partial`` 是逐项兑付引入的：有一部分行发了，剩下的
#: 仍然要留。``draft`` 是老师自己还没想好的，不该占料；``issued`` 全发完了。
OPEN_STATUSES = ("submitted", "partial")

#: 路由范围 → 需求单来源类别。对不上的范围（科室/个人）无法从单据反查，
#: 不参与计算——宁可少保一点，也不猜。
SCOPE_TO_SOURCE_KIND = {
    "course": "teaching",
    "course_class": "teaching",
    "project": "research",
}

#: 余量的浮点容差。
_EPS = 1e-9


class DemandReserve:
    """按学年统计的保底量。可作为 ``AcceptanceDesk(reserve=...)`` 注入。"""

    def __init__(
        self,
        database: Optional[Database] = None,
        routes=None,
        today: Optional[date] = None,
    ) -> None:
        self.db = database or Database()
        self.routes = routes or custodian_route_repository
        self._today = today

    def __call__(self, query: ReserveQuery) -> Optional[Quantity]:
        semester = AcademicYear.current(self._today).label
        scopes = self._scopes_of(query.custodian.name)
        if not scopes:
            return None

        sheet_ids = self._open_sheets_for(scopes, semester, query.exclude_source)
        if not sheet_ids:
            return None
        return self._quantity_of(sheet_ids, query.substance)

    # ---------------------------------------------------------------- 范围
    def _scopes_of(self, custodian_name: str) -> list[tuple[str, str]]:
        """这个保管人负责的 (scope_type, scope_key)。"""
        if not (custodian_name or "").strip():
            return []
        rows = self.routes.rows()
        return [
            (row["scope_type"], row["scope_key"])
            for row in rows
            if (row.get("custodian") or "").strip() == custodian_name.strip()
            and row.get("scope_type") in SCOPE_TO_SOURCE_KIND
            and (row.get("scope_key") or "").strip()
        ]

    @staticmethod
    def matches(scope_key: str, source_code: str) -> bool:
        """一条范围是否覆盖这个来源。

        两级：整键命中，或来源是「课程/实验」而范围是课程名。与
        :meth:`capabilities.circulation.routing.SourceRouter` 的 ``_lookup``
        是同一规则——路由说归谁、保底就算给谁，两处不能分叉。
        """
        if not scope_key or not source_code:
            return False
        return source_code == scope_key or source_code.startswith(scope_key + "/")

    # ---------------------------------------------------------------- 单据
    def _open_sheets_for(
        self,
        scopes: list[tuple[str, str]],
        semester: str,
        exclude_source: Optional[tuple[str, str]],
    ) -> list[int]:
        placeholders = ",".join("?" for _ in OPEN_STATUSES)
        try:
            rows = self.db.execute_query(
                f"SELECT id, source_kind, source_code FROM requirement_sheet "
                f"WHERE academic_year = ? AND status IN ({placeholders})",
                (semester, *OPEN_STATUSES),
            )
        except Exception as exc:
            logger.warning(
                f"保底查询失败（requirement_sheet 可能缺 academic_year 列，"
                f"重启应用即可）：{exc}"
            )
            return []

        exclude_kind = exclude_source[0] if exclude_source else None
        exclude_code = exclude_source[1] if exclude_source else None

        hits: list[int] = []
        for row in rows:
            kind = (row.get("source_kind") or "").strip()
            code = (row.get("source_code") or "").strip()
            # 当前这张单自己不算保底，否则需求量永远抽不出来
            if exclude_code and code == exclude_code and kind == exclude_kind:
                continue
            if any(
                SCOPE_TO_SOURCE_KIND[scope_type] == kind and self.matches(scope_key, code)
                for scope_type, scope_key in scopes
            ):
                hits.append(int(row["id"]))
        return hits

    def _quantity_of(self, sheet_ids: list[int], ref: SubstanceRef) -> Optional[Quantity]:
        """这些单里该物质**还没兑付**的合计。量纲按第一行同量纲的来。

        逐行扣减已发量，不是按单全量。分两次发料时第二次的保底必须只剩
        尾数——否则已经交到老师手上的那部分会让系统以为还欠着，抽卡时把
        本可以动的料锁住。
        """
        placeholders = ",".join("?" for _ in sheet_ids)
        try:
            rows = self.db.execute_query(
                f"SELECT quantity, unit, "
                f"COALESCE(issued_quantity, 0) AS issued_quantity "
                f"FROM requirement_line "
                f"WHERE sheet_id IN ({placeholders}) AND substance_key = ?",
                (*sheet_ids, ref.key),
            )
        except Exception as exc:
            logger.warning(f"保底明细查询失败: {exc}")
            return None

        total: Optional[Quantity] = None
        for row in rows:
            try:
                unit = parse_unit(row.get("unit") or "g")
            except Exception:
                continue
            value = row.get("quantity")
            if value in (None, ""):
                continue
            remaining = float(value) - float(row.get("issued_quantity") or 0)
            if remaining <= _EPS:
                continue  # 这一项已兑完，不占料
            if total is None:
                total = Quantity(0, unit)
            if total.unit.dimension is not unit.dimension:
                # 跨量纲不在这里折算：换算要物性，中台才有（SupplyEvaluator）
                continue
            total = total + Quantity(remaining, unit)
        return total


demand_reserve = DemandReserve()


__all__ = ["DemandReserve", "demand_reserve"]
