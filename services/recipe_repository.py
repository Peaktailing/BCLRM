"""仓储实现：SQLite 行 ↔ 领域对象。

这是整个架构里唯一同时认识「表结构」和「领域对象」的地方。上层拿到的
永远是 ``Recipe`` / ``RequirementSheet``，看不到 dict、看不到列名，也
看不到中文状态词。

对应关系：
``business/ports.py`` 定义协议 → 本模块实现 → ``business/*_service.py`` 注入
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from db.database import db
from domain.batch import BatchScale
from domain.recipe import Recipe, RecipeComponent, RecipeStatus, SourceKind, SourceRef
from domain.requirement import RequirementLine, RequirementSheet
from services.base.recipe_service import recipe_component_service, recipe_service
from services.core.requirement_sheet_service import (
    decode_warnings,
    encode_warnings,
    requirement_line_service,
    requirement_sheet_service,
)
from utils.error_handler import logger
from utils.field_mapper import (
    RecipeField,
    RequirementLineField,
    RequirementSheetField,
)


class SqliteRecipeRepository:
    """配方仓储（SQLite）。"""

    def __init__(self, recipes=None, components=None) -> None:
        self._recipes = recipes or recipe_service
        self._components = components or recipe_component_service

    # ---------------------------------------------------------------- 读
    def get(self, key: str) -> Optional[Recipe]:
        row = self._recipes.get_by_key(key)
        if not row:
            return None
        return self._to_domain(row)

    def list(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        source_kind: Optional[str] = None,
        limit: int = 200,
    ) -> List[Recipe]:
        rows = self._recipes.list_recipes(keyword, status, source_kind, limit)
        recipes: List[Recipe] = []
        for row in rows:
            try:
                recipes.append(self._to_domain(row))
            except Exception as exc:  # 单行脏数据不拖垮整个列表
                logger.error(f"配方行解析失败 key={row.get('recipe_key')}: {exc}", exception=exc)
        return recipes

    def exists(self, key: str) -> bool:
        return self._recipes.get_by_key(key) is not None

    # ---------------------------------------------------------------- 写
    def save(self, recipe: Recipe, operator: str = "") -> Recipe:
        record = self._to_record(recipe)
        with db.transaction():
            recipe_id = self._recipes.upsert(record, operator)
            self._components.replace_all(
                recipe_id, [c.to_record() for c in recipe.components]
            )
        return recipe

    def delete(self, key: str) -> bool:
        row = self._recipes.get_by_key(key)
        if not row:
            return False
        recipe_id = int(row[RecipeField.ID])
        with db.transaction():
            self._components.delete_of(recipe_id)
            return self._recipes.delete(recipe_id)

    def set_status(self, key: str, status: RecipeStatus, operator: str = "") -> bool:
        return self._recipes.set_status(key, status.value, operator)

    # ---------------------------------------------------------------- 转换
    def _to_domain(self, row: Dict[str, Any]) -> Recipe:
        recipe_id = int(row[RecipeField.ID])
        component_rows = self._components.list_of(recipe_id)
        components = tuple(
            RecipeComponent.from_record(item) for item in component_rows
        )
        source_kind = row.get(RecipeField.SOURCE_KIND)
        source = (
            SourceRef(
                SourceKind(source_kind),
                row.get(RecipeField.SOURCE_CODE) or "",
                row.get(RecipeField.SOURCE_TITLE) or "",
            )
            if source_kind
            else None
        )
        status_value = row.get(RecipeField.STATUS) or RecipeStatus.DRAFT.value
        return Recipe(
            key=row[RecipeField.RECIPE_KEY],
            title=row.get(RecipeField.TITLE) or "",
            components=components,
            version=int(row.get(RecipeField.VERSION) or 1),
            status=RecipeStatus(status_value),
            source=source,
            owner=row.get(RecipeField.OWNER) or "",
            note=row.get(RecipeField.NOTE) or "",
        )

    @staticmethod
    def _to_record(recipe: Recipe) -> Dict[str, Any]:
        return {
            RecipeField.RECIPE_KEY: recipe.key,
            RecipeField.TITLE: recipe.title,
            RecipeField.VERSION: recipe.version,
            RecipeField.STATUS: recipe.status.value,
            RecipeField.SOURCE_KIND: recipe.source.kind.value if recipe.source else None,
            RecipeField.SOURCE_CODE: recipe.source.code if recipe.source else None,
            RecipeField.SOURCE_TITLE: recipe.source.title if recipe.source else None,
            RecipeField.OWNER: recipe.owner,
            RecipeField.NOTE: recipe.note,
        }


class SqliteRequirementRepository:
    """需求单仓储（SQLite，只追加）。"""

    def __init__(self, sheets=None, lines=None, recipes=None) -> None:
        self._sheets = sheets or requirement_sheet_service
        self._lines = lines or requirement_line_service
        self._recipes = recipes or recipe_service

    # ---------------------------------------------------------------- 写
    def save(
        self,
        sheet: RequirementSheet,
        requester: str,
        snapshot_data: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        prefix = f"RQ{datetime.now():%Y%m%d}-"
        sequence = self._sheets.next_sequence(prefix)
        sheet_number = f"{prefix}{sequence:04d}"

        recipe_row = self._recipes.get_by_key(sheet.recipe_key)
        scale_record = sheet.scale.to_record()

        record = {
            RequirementSheetField.SHEET_NUMBER: sheet_number,
            RequirementSheetField.RECIPE_ID: (
                int(recipe_row[RecipeField.ID]) if recipe_row else None
            ),
            RequirementSheetField.RECIPE_KEY: sheet.recipe_key,
            RequirementSheetField.TITLE: sheet.title,
            # 单据状态归流转网关管理，需求单落库时是「已算出未提交」
            RequirementSheetField.STATUS: "draft",
            RequirementSheetField.PERSONS: scale_record.get("persons"),
            RequirementSheetField.BATCHES: scale_record.get("batches"),
            RequirementSheetField.VESSEL_VOLUME: scale_record.get("vessel_volume"),
            RequirementSheetField.VESSEL_UNIT: scale_record.get("vessel_unit"),
            RequirementSheetField.SCALE_LABEL: scale_record.get("label"),
            RequirementSheetField.REQUESTER: requester,
            RequirementSheetField.SOURCE_KIND: (
                sheet.source.kind.value if sheet.source else None
            ),
            RequirementSheetField.SOURCE_CODE: sheet.source.code if sheet.source else None,
            RequirementSheetField.WARNINGS: encode_warnings(sheet.warnings),
        }

        with db.transaction():
            sheet_id = self._sheets.create(record)
            if not sheet_id:
                raise RuntimeError("需求单写入失败")
            line_records = []
            for line in sheet.lines:
                item = line.to_record()
                extra = (snapshot_data or {}).get(line.key) or {}
                item[RequirementLineField.AVAILABLE_QUANTITY] = extra.get("available")
                item[RequirementLineField.GAP_QUANTITY] = extra.get("gap")
                item[RequirementLineField.COVERAGE_RATIO] = extra.get("coverage")
                line_records.append(item)
            self._lines.replace_all(sheet_id, line_records)

        return sheet_number

    # ---------------------------------------------------------------- 读
    def get(self, sheet_number: str) -> Optional[RequirementSheet]:
        row = self._sheets.get_by_number(sheet_number)
        if not row:
            return None
        lines = tuple(
            RequirementLine.from_record(item)
            for item in self._lines.list_of(int(row[RequirementSheetField.ID]))
        )
        scale = BatchScale.from_record(
            {
                "persons": row.get(RequirementSheetField.PERSONS),
                "batches": row.get(RequirementSheetField.BATCHES),
                "vessel_volume": row.get(RequirementSheetField.VESSEL_VOLUME),
                "vessel_unit": row.get(RequirementSheetField.VESSEL_UNIT),
                "label": row.get(RequirementSheetField.SCALE_LABEL),
            }
        )
        source_kind = row.get(RequirementSheetField.SOURCE_KIND)
        source = (
            SourceRef(SourceKind(source_kind), row.get(RequirementSheetField.SOURCE_CODE) or "")
            if source_kind
            else None
        )
        return RequirementSheet(
            recipe_key=row.get(RequirementSheetField.RECIPE_KEY) or "",
            title=row.get(RequirementSheetField.TITLE) or "",
            scale=scale,
            lines=lines,
            source=source,
            warnings=tuple(decode_warnings(row.get(RequirementSheetField.WARNINGS))),
        )

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._sheets.list_recent(limit)
        return [
            {
                "sheet_number": row.get(RequirementSheetField.SHEET_NUMBER),
                "title": row.get(RequirementSheetField.TITLE),
                "recipe_key": row.get(RequirementSheetField.RECIPE_KEY),
                "requester": row.get(RequirementSheetField.REQUESTER),
                "status": row.get(RequirementSheetField.STATUS),
                "created_at": row.get("created_at"),
                "persons": row.get(RequirementSheetField.PERSONS),
                "batches": row.get(RequirementSheetField.BATCHES),
            }
            for row in rows
        ]

    def set_status(self, sheet_number: str, status: str, operator: str = "") -> bool:
        return self._sheets.set_status(sheet_number, status, operator)


__all__ = ["SqliteRecipeRepository", "SqliteRequirementRepository"]
