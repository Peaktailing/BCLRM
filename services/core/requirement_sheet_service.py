"""需求单与明细的数据访问服务。

需求单是只追加的快照：一旦算出就冻结，后续库存变化不回写。要重算就
产生新单——这是「当时按什么算的能复盘」的前提。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from db.base_service import BaseService
from db.database import db
from utils.audit import audit
from utils.field_mapper import RequirementLineField, RequirementSheetField

_SHEET_TABLE = "requirement_sheet"
_LINE_TABLE = "requirement_line"

#: 明细行的兑付状态。**兑付粒度是行，不是单头**——一张单可能今天只发得出
#: 5 项，剩下 15 项要等料；整单置 issued 会把那 15 项静默吞掉。单头状态
#: 由这些行状态聚合出来，不独立驱动。
LINE_OPEN = "open"
LINE_PARTIAL = "partial"
LINE_ISSUED = "issued"

#: 单头状态。``partial`` 是新增的：有一部分行兑完了，这张单还没结。
SHEET_PARTIAL = "partial"

#: 兑付量的浮点容差。g 与 mg 换算会带尾数，卡死等号会永远兑不完。
_QTY_EPS = 1e-9

_LINE_COLUMNS = {
    RequirementLineField.SEQ,
    RequirementLineField.SUBSTANCE_KEY,
    RequirementLineField.DISPLAY_NAME,
    RequirementLineField.CAS_NUMBER,
    RequirementLineField.ROLE,
    RequirementLineField.QUANTITY,
    RequirementLineField.UNIT,
    RequirementLineField.BASIS_TEXT,
    RequirementLineField.EXPLANATION,
    RequirementLineField.PURITY_REQUIRED,
    RequirementLineField.IS_CONTROLLED,
    RequirementLineField.AVAILABLE_QUANTITY,
    RequirementLineField.GAP_QUANTITY,
    RequirementLineField.COVERAGE_RATIO,
}


class RequirementSheetService(BaseService):
    """需求单头数据访问。"""

    def __init__(self, database=None) -> None:
        super().__init__(_SHEET_TABLE, database or db)

    def get_by_number(self, sheet_number: str) -> Optional[Dict[str, Any]]:
        if not sheet_number:
            return None
        return self.get_by_field(RequirementSheetField.SHEET_NUMBER, sheet_number)

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.get_all(order_by="created_at DESC", limit=limit)

    def list_by_recipe(self, recipe_key: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.get_all_by_field(
            RequirementSheetField.RECIPE_KEY, recipe_key, order_by="created_at DESC"
        )[:limit]

    def next_sequence(self, prefix: str) -> int:
        """当日流水号（同前缀的最大值 +1）。"""
        max_value = self.get_max_value_by_prefix(
            RequirementSheetField.SHEET_NUMBER, prefix
        )
        if not max_value:
            return 1
        try:
            return int(max_value[len(prefix):]) + 1
        except (TypeError, ValueError):
            return 1

    def set_status(self, sheet_number: str, status: str, operator: str = "") -> bool:
        row = self.get_by_number(sheet_number)
        if not row:
            return False
        ok = self.update(row[RequirementSheetField.ID], {RequirementSheetField.STATUS: status})
        if ok:
            audit(operator, "变更需求单状态", "requirement_sheet", sheet_number, status)
        return ok

    def promote_to_submitted(self, sheet_number: str, operator: str = "") -> bool:
        """草稿 → 已提交。受理这张申请的那一刻调用。

        **只推草稿**。已经 submitted/partial/issued 的单不碰：把它们打回
        ``submitted`` 会把兑付进度踩平，保底又把已经发出去的料算成欠量。
        """
        row = self.get_by_number(sheet_number)
        if not row:
            return False
        if (row.get(RequirementSheetField.STATUS) or "").strip() not in ("", "draft"):
            return False
        return self.set_status(sheet_number, "submitted", operator)

    # ------------------------------------------------------------ 单头聚合
    def lines_of(self, sheet_id: int) -> List[Dict[str, Any]]:
        """这张单的全部明细行（含兑付进度）。

        单头要聚合状态就得看得见明细，所以这里跨表只读查一次。反向的
        「行改完再来改单头」不这么做——那会绕开单据服务自己写状态。
        """
        return self.db.execute_query(
            "SELECT id, seq, substance_key, display_name, quantity, unit, "
            "COALESCE(issued_quantity, 0) AS issued_quantity, "
            "COALESCE(status, 'open') AS status, order_number "
            "FROM requirement_line WHERE sheet_id = ? ORDER BY seq ASC, id ASC",
            (sheet_id,),
        )

    def recount_status(self, sheet_id: int) -> Optional[str]:
        """按明细行的兑付进度推单头状态。

        Returns:
            ``issued``（全部行兑完）/ ``partial``（有行兑过但没兑完）/
            ``None``（一眼没兑过，不改单头——draft 与 submitted 的区分是
            老师那边的意图，不该被一次空聚合抹平）。
        """
        rows = self.lines_of(sheet_id)
        if not rows:
            return None
        done = sum(1 for row in rows if (row.get("status") or "") == LINE_ISSUED)
        touched = sum(
            1 for row in rows if float(row.get("issued_quantity") or 0) > _QTY_EPS
        )
        if done == len(rows):
            status = LINE_ISSUED
        elif touched:
            status = SHEET_PARTIAL
        else:
            return None
        self.update(sheet_id, {RequirementSheetField.STATUS: status})
        return status


class RequirementLineService(BaseService):
    """需求明细数据访问。"""

    def __init__(self, database=None) -> None:
        super().__init__(_LINE_TABLE, database or db)

    def list_of(self, sheet_id: int) -> List[Dict[str, Any]]:
        return self.get_all_by_field(
            RequirementLineField.SHEET_ID, sheet_id, order_by="seq ASC"
        )

    def replace_all(self, sheet_id: int, records: List[Dict[str, Any]]) -> int:
        """整单重写明细。兑付三列不在白名单里，重写即归零——重算就是新账。"""
        self.delete_by_field(RequirementLineField.SHEET_ID, sheet_id)
        written = 0
        for record in records:
            payload = {k: v for k, v in record.items() if k in _LINE_COLUMNS}
            payload[RequirementLineField.SHEET_ID] = sheet_id
            if self.create(payload):
                written += 1
        return written

    # ------------------------------------------------------------ 逐项兑付
    @staticmethod
    def remaining_of(row: Dict[str, Any]) -> float:
        """这条行还欠多少（需求量 − 已兑付量），不会为负。"""
        need = float(row.get(RequirementLineField.QUANTITY) or 0)
        done = float(row.get(RequirementLineField.ISSUED_QUANTITY) or 0)
        return max(need - done, 0.0)

    def settle(
        self, line_id: int, add_quantity: float, order_number: str = ""
    ) -> Optional[Dict[str, Any]]:
        """把一条行的兑付量往前推，并同步行状态。

        量的单位必须与 ``quantity`` 同——调用方先换回行单位再传。跨量纲
        （g ↔ mL）在兑付这一步已经被拒了，见 ``RequirementIssueService``。
        """
        row = self.get_by_id(line_id)
        if not row:
            return None
        need = float(row.get(RequirementLineField.QUANTITY) or 0)
        done = float(row.get(RequirementLineField.ISSUED_QUANTITY) or 0) + float(add_quantity)
        # 兜底再夹一次：服务层已经按余量截断过，这里防的是调用方绕过
        done = min(max(done, 0.0), need)
        status = LINE_ISSUED if need - done <= _QTY_EPS else LINE_PARTIAL
        payload = {
            RequirementLineField.ISSUED_QUANTITY: done,
            RequirementLineField.STATUS: status,
        }
        if order_number:
            payload[RequirementLineField.ORDER_NUMBER] = order_number
        if not self.update(line_id, payload):
            return None
        return {"issued_quantity": done, "status": status, "quantity": need}


def encode_warnings(warnings: List[str]) -> str:
    """告警列表 → JSON 文本（列是 TEXT，保持可读）。"""
    return json.dumps(list(warnings or []), ensure_ascii=False)


def decode_warnings(text: Optional[str]) -> List[str]:
    if not text:
        return []
    try:
        value = json.loads(text)
        return [str(item) for item in value] if isinstance(value, list) else []
    except (TypeError, ValueError):
        return [text]


# 全局实例
requirement_sheet_service = RequirementSheetService()
requirement_line_service = RequirementLineService()

__all__ = [
    "RequirementSheetService",
    "RequirementLineService",
    "requirement_sheet_service",
    "requirement_line_service",
    "LINE_OPEN",
    "LINE_PARTIAL",
    "LINE_ISSUED",
    "SHEET_PARTIAL",
    "encode_warnings",
    "decode_warnings",
]
