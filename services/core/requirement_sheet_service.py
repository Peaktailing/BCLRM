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


class RequirementLineService(BaseService):
    """需求明细数据访问。"""

    def __init__(self, database=None) -> None:
        super().__init__(_LINE_TABLE, database or db)

    def list_of(self, sheet_id: int) -> List[Dict[str, Any]]:
        return self.get_all_by_field(
            RequirementLineField.SHEET_ID, sheet_id, order_by="seq ASC"
        )

    def replace_all(self, sheet_id: int, records: List[Dict[str, Any]]) -> int:
        self.delete_by_field(RequirementLineField.SHEET_ID, sheet_id)
        written = 0
        for record in records:
            payload = {k: v for k, v in record.items() if k in _LINE_COLUMNS}
            payload[RequirementLineField.SHEET_ID] = sheet_id
            if self.create(payload):
                written += 1
        return written


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
    "encode_warnings",
    "decode_warnings",
]
