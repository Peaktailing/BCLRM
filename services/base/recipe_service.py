"""配方与配方组分的数据访问服务。

只管表、不管规则：这里不判断「当量能不能算」，只负责把一行行记录
读出来、写进去。对象化转换在 ``services/recipe_repository.py``，
业务规则在 ``business/recipe_service.py``。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from db.base_service import BaseService
from db.database import db
from utils.audit import audit
from utils.error_handler import logger
from utils.field_mapper import RecipeComponentField, RecipeField

_TABLE = "recipe"
_COMPONENT_TABLE = "recipe_component"

#: 允许写入的列（防止调用方塞入表里没有的键）
_COMPONENT_COLUMNS = {
    RecipeComponentField.SEQ,
    RecipeComponentField.ROLE,
    RecipeComponentField.SUBSTANCE_KEY,
    RecipeComponentField.DISPLAY_NAME,
    RecipeComponentField.CAS_NUMBER,
    RecipeComponentField.FORMULA,
    RecipeComponentField.AMOUNT_TYPE,
    RecipeComponentField.AMOUNT_VALUE,
    RecipeComponentField.AMOUNT_UNIT,
    RecipeComponentField.REF_KEY,
    RecipeComponentField.CONCENTRATION,
    RecipeComponentField.CONCENTRATION_UNIT,
    RecipeComponentField.COEFFICIENT,
    RecipeComponentField.PURITY_REQUIRED,
    RecipeComponentField.NOTE,
}


class RecipeService(BaseService):
    """配方表数据访问。"""

    def __init__(self, database=None) -> None:
        super().__init__(_TABLE, database or db)

    # ---------------------------------------------------------------- 查询
    def get_by_key(self, recipe_key: str) -> Optional[Dict[str, Any]]:
        if not recipe_key:
            return None
        return self.get_by_field(RecipeField.RECIPE_KEY, recipe_key)

    def list_recipes(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        source_kind: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        conditions: List[Dict[str, Any]] = []
        if status:
            conditions.append({"field": RecipeField.STATUS, "value": status})
        if source_kind:
            conditions.append({"field": RecipeField.SOURCE_KIND, "value": source_kind})
        if keyword:
            conditions.append(
                {
                    "field": RecipeField.TITLE,
                    "value": keyword,
                    "match_type": "keyword",
                    "keyword_fields": [RecipeField.TITLE, RecipeField.RECIPE_KEY],
                }
            )
        return self.search_multi_condition(
            conditions, order_by="updated_at DESC", limit=limit
        )

    def versions_of(self, recipe_key: str) -> List[Dict[str, Any]]:
        """同键历史版本（若是「同键覆盖」策略，通常只有一条）。"""
        return self.get_all_by_field(RecipeField.RECIPE_KEY, recipe_key, order_by="version DESC")

    # ---------------------------------------------------------------- 写入
    def upsert(self, record: Dict[str, Any], operator: str = "") -> int:
        """按业务键写入：存在则更新，不存在则新建。返回记录 id。"""
        key = record.get(RecipeField.RECIPE_KEY)
        if not key:
            raise ValueError("配方缺少 recipe_key")
        existing = self.get_by_key(key)
        if existing:
            payload = {k: v for k, v in record.items() if k != RecipeField.RECIPE_KEY}
            if payload:
                self.update(existing[RecipeField.ID], payload)
            audit(operator, "更新配方", "recipe", key,
                  f"{record.get(RecipeField.TITLE, '')} v{record.get(RecipeField.VERSION, '')}")
            return int(existing[RecipeField.ID])
        new_id = self.create(record) or 0
        audit(operator, "新建配方", "recipe", key,
              f"{record.get(RecipeField.TITLE, '')} v{record.get(RecipeField.VERSION, '')}")
        return int(new_id)

    def set_status(self, recipe_key: str, status: str, operator: str = "") -> bool:
        row = self.get_by_key(recipe_key)
        if not row:
            return False
        ok = self.update(row[RecipeField.ID], {RecipeField.STATUS: status})
        if ok:
            audit(operator, "变更配方状态", "recipe", recipe_key, status)
        return ok

    def archive(self, recipe_key: str, operator: str = "") -> bool:
        return self.set_status(recipe_key, "archived", operator)

    def next_version(self, recipe_key: str) -> int:
        row = self.get_by_key(recipe_key)
        if not row:
            return 1
        return int(row.get(RecipeField.VERSION) or 1) + 1


class RecipeComponentService(BaseService):
    """配方组分表数据访问。"""

    def __init__(self, database=None) -> None:
        super().__init__(_COMPONENT_TABLE, database or db)

    # ---------------------------------------------------------------- 查询
    def list_of(self, recipe_id: int) -> List[Dict[str, Any]]:
        return self.get_all_by_field(
            RecipeComponentField.RECIPE_ID, recipe_id, order_by="seq ASC"
        )

    # ---------------------------------------------------------------- 写入
    def replace_all(self, recipe_id: int, records: List[Dict[str, Any]]) -> int:
        """整组替换：先删旧行再插新行（配方是不可变整体，组分不做增量）。"""
        self.delete_by_field(RecipeComponentField.RECIPE_ID, recipe_id)
        written = 0
        for record in records:
            payload = {
                key: value for key, value in record.items() if key in _COMPONENT_COLUMNS
            }
            payload[RecipeComponentField.RECIPE_ID] = recipe_id
            if self.create(payload):
                written += 1
        logger.info(f"配方组分已写入 recipe_id={recipe_id} 共 {written} 行")
        return written

    def delete_of(self, recipe_id: int) -> bool:
        return self.delete_by_field(RecipeComponentField.RECIPE_ID, recipe_id)


# 全局实例（与项目其他服务保持一致的使用方式）
recipe_service = RecipeService()
recipe_component_service = RecipeComponentService()

__all__ = ["RecipeService", "RecipeComponentService", "recipe_service", "recipe_component_service"]
