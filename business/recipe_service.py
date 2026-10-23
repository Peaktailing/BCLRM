"""配方业务服务：配方编制与校验的用例编排。

职责边界很清楚：

- **不做计算**：算多少是计量中台的事（``capabilities.metering``）。
- **不写 SQL**：存取是仓储的事（``business.ports`` + ``services``）。
- **只做编排与决策**：校验不过就不落库、内容没变就不升版、谁能改配方
  由权限规则决定。

返回统一的 :class:`ServiceResult`，页面直接判 ``success`` 与读 ``data``。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

from capabilities.metering import MeteringEngine
from domain.amount import AmountError, AmountSpec
from domain.batch import BatchScale
from domain.recipe import (
    Recipe,
    RecipeComponent,
    RecipeError,
    RecipeStatus,
    SourceKind,
    SourceRef,
    ValidationReport,
)
from domain.substance import ComponentRole, SubstanceRef
from utils.audit import audit
from utils.error_handler import ServiceResult, handle_exception, logger
from utils.permission_guard import enforce_role

#: 可维护配方的角色（教师及以上；脚本/测试无上下文时自动放行）
RECIPE_ROLES = ("teacher", "admin", "super_admin")


class RecipeBusinessService:
    """配方用例服务。"""

    def __init__(self, repository=None, resolver=None) -> None:
        self._repository = repository
        self._resolver = resolver

    # ---------------------------------------------------------------- 依赖
    @property
    def repository(self):
        """延迟装配默认仓储：测试可注入，生产自动用 SQLite 实现。"""
        if self._repository is None:
            from services.recipe_repository import SqliteRecipeRepository
            self._repository = SqliteRecipeRepository()
        return self._repository

    @property
    def resolver(self):
        if self._resolver is None:
            from services.substance_catalog import build_resolver
            self._resolver = build_resolver()
        return self._resolver

    # ---------------------------------------------------------------- 查询
    @handle_exception(context="查询配方列表")
    def list_recipes(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        source_kind: Optional[str] = None,
        limit: int = 200,
    ) -> ServiceResult:
        recipes = self.repository.list(keyword, status, source_kind, limit)
        rows = [self._summary(recipe) for recipe in recipes]
        message = f"共 {len(rows)} 个配方" if rows else "还没有配方"
        return ServiceResult.ok(data={"items": rows, "total": len(rows)}, message=message)

    @handle_exception(context="读取配方")
    def get_recipe(self, recipe_key: str) -> ServiceResult:
        recipe = self.repository.get(recipe_key)
        if recipe is None:
            return ServiceResult.fail(
                message=f"配方不存在：{recipe_key}", error_code="RECIPE_NOT_FOUND"
            )
        report = recipe.validate()
        return ServiceResult.ok(
            data={"recipe": recipe, "detail": self._detail(recipe), "validation": report},
            message=recipe.describe(),
        )

    # ---------------------------------------------------------------- 保存
    @handle_exception(context="保存配方")
    def save_recipe(self, payload: Dict[str, Any], operator: str = "") -> ServiceResult:
        """新建或修改配方。

        版本策略：内容指纹变了才升版；没变则原地返回，避免无意义的版本膨胀。
        """
        enforce_role(*RECIPE_ROLES, action="维护实验配方")

        try:
            incoming = self.build_recipe(payload, operator)
        except (RecipeError, AmountError, ValueError, KeyError) as exc:
            return ServiceResult.fail(message=f"配方内容有误：{exc}", error_code="RECIPE_INVALID")

        report = incoming.validate()
        if not report.is_valid:
            return ServiceResult.fail(
                message=f"配方校验未通过：{report.errors[0]}",
                error_code="RECIPE_INVALID",
                data={"issues": [self._issue(item) for item in report.issues]},
            )

        existing = self.repository.get(incoming.key)
        if existing is not None:
            if existing.fingerprint() == incoming.fingerprint() and (
                existing.title == incoming.title
            ):
                return ServiceResult.ok(
                    data={"recipe": existing, "detail": self._detail(existing)},
                    message="内容没有变化，未产生新版本",
                )
            incoming = self._upgrade(existing, incoming)

        saved = self.repository.save(incoming, operator)
        audit(
            operator,
            "保存配方",
            "recipe",
            saved.key,
            f"{saved.title} v{saved.version}（{len(saved.material_components)} 项备料）",
        )
        warnings = [self._issue(item) for item in report.warnings]
        return ServiceResult.ok(
            data={"recipe": saved, "detail": self._detail(saved), "warnings": warnings},
            message=f"已保存「{saved.title}」v{saved.version}"
            + (f"，{len(warnings)} 条提示" if warnings else ""),
        )

    @handle_exception(context="校验配方")
    def validate_recipe(self, recipe_key: str) -> ServiceResult:
        recipe = self.repository.get(recipe_key)
        if recipe is None:
            return ServiceResult.fail(
                message=f"配方不存在：{recipe_key}", error_code="RECIPE_NOT_FOUND"
            )
        report = recipe.validate()
        data = {
            "is_valid": report.is_valid,
            "summary": report.summary(),
            "issues": [self._issue(item) for item in report.issues],
        }
        return ServiceResult.ok(
            data=data,
            message=report.summary() if report.is_valid else f"校验未通过：{report.errors[0]}",
        )

    @handle_exception(context="变更配方状态")
    def change_status(self, recipe_key: str, status: str, operator: str = "") -> ServiceResult:
        enforce_role(*RECIPE_ROLES, action="变更配方状态")
        recipe = self.repository.get(recipe_key)
        if recipe is None:
            return ServiceResult.fail(
                message=f"配方不存在：{recipe_key}", error_code="RECIPE_NOT_FOUND"
            )
        try:
            target = RecipeStatus(status)
        except ValueError:
            return ServiceResult.fail(message=f"未知状态：{status}", error_code="BAD_STATUS")

        if target is RecipeStatus.VALIDATED:
            report = recipe.validate()
            if not report.is_valid:
                return ServiceResult.fail(
                    message=f"校验未通过，不能置为已验证：{report.errors[0]}",
                    error_code="RECIPE_INVALID",
                )

        updated = recipe.with_status(target)
        self.repository.save(updated, operator)
        audit(operator, "变更配方状态", "recipe", recipe_key, target.value)
        return ServiceResult.ok(
            data={"recipe": updated}, message=f"配方已置为「{target.label}」"
        )

    # ---------------------------------------------------------------- 组装
    def build_recipe(self, payload: Dict[str, Any], operator: str = "") -> Recipe:
        """把页面/接口传来的字典装配成聚合根（不落库）。"""
        key = (payload.get("key") or payload.get("recipe_key") or "").strip()
        if not key:
            raise RecipeError("缺少配方关键字")

        title = (payload.get("title") or "").strip()
        if not title:
            raise RecipeError("缺少配方标题")

        raw_components = payload.get("components") or []
        if not isinstance(raw_components, (list, tuple)) or not raw_components:
            raise RecipeError("至少要有一个组分")

        components = tuple(
            self._component(item, index)
            for index, item in enumerate(raw_components)
        )

        return Recipe(
            key=key,
            title=title,
            components=components,
            version=int(payload.get("version") or 1),
            status=RecipeStatus(payload.get("status") or RecipeStatus.DRAFT.value),
            source=self._source(payload.get("source")),
            owner=(payload.get("owner") or operator or "").strip(),
            note=(payload.get("note") or "").strip(),
        )

    @staticmethod
    def _component(item: Dict[str, Any], index: int) -> RecipeComponent:
        substance = item.get("substance") or {}
        ref = SubstanceRef.of(
            substance.get("name") or item.get("name") or "",
            substance.get("cas") or item.get("cas"),
            substance.get("formula") or item.get("formula"),
        )
        try:
            role = ComponentRole(item.get("role") or ComponentRole.REAGENT.value)
        except ValueError as exc:
            raise RecipeError(f"第 {index + 1} 行角色非法：{item.get('role')}") from exc

        amount_payload = item.get("amount") if isinstance(item.get("amount"), dict) else item
        amount = AmountSpec.from_record(amount_payload)

        try:
            coefficient = Decimal(str(item.get("coefficient") or 1))
        except InvalidOperation as exc:
            raise RecipeError(f"第 {index + 1} 行化学计量系数非法") from exc

        purity = item.get("purity_required")
        return RecipeComponent(
            substance=ref,
            role=role,
            amount=amount,
            seq=int(item.get("seq") if item.get("seq") is not None else index),
            coefficient=coefficient,
            purity_required=Decimal(str(purity)) if purity not in (None, "") else None,
            note=(item.get("note") or "").strip(),
        )

    @staticmethod
    def _source(raw: Optional[Dict[str, Any]]) -> Optional[SourceRef]:
        if not raw:
            return None
        try:
            kind = SourceKind(raw.get("kind") or SourceKind.MANUAL.value)
        except ValueError:
            kind = SourceKind.MANUAL
        return SourceRef(kind, (raw.get("code") or "").strip(), (raw.get("title") or "").strip())

    @staticmethod
    def _upgrade(existing: Recipe, incoming: Recipe) -> Recipe:
        """内容变化时升版：版本号 +1，状态回到草稿（需重新校验）。"""
        return Recipe(
            key=incoming.key,
            title=incoming.title,
            components=incoming.components,
            version=existing.version + 1,
            status=RecipeStatus.DRAFT,
            source=incoming.source or existing.source,
            owner=incoming.owner or existing.owner,
            note=incoming.note,
        )

    # ---------------------------------------------------------------- DTO
    @staticmethod
    def _summary(recipe: Recipe) -> Dict[str, Any]:
        report = recipe.validate()
        return {
            "key": recipe.key,
            "title": recipe.title,
            "version": recipe.version,
            "status": recipe.status.value,
            "status_label": recipe.status.label,
            "source": recipe.source.describe() if recipe.source else "",
            "source_kind": recipe.source.kind.value if recipe.source else "",
            "component_count": len(recipe.components),
            "material_count": len(recipe.material_components),
            "is_valid": report.is_valid,
            "issue_count": len(report.issues),
            "owner": recipe.owner,
        }

    @staticmethod
    def _detail(recipe: Recipe) -> Dict[str, Any]:
        return {
            "key": recipe.key,
            "title": recipe.title,
            "version": recipe.version,
            "status": recipe.status.value,
            "status_label": recipe.status.label,
            "source": recipe.source.describe() if recipe.source else "",
            "note": recipe.note,
            "components": [
                {
                    "seq": component.seq,
                    "name": component.substance.name or component.substance.key,
                    "cas": component.substance.cas.value if component.substance.cas else "",
                    "formula": component.substance.formula.text if component.substance.formula else "",
                    "role": component.role.value,
                    "role_label": component.role.label,
                    "amount": component.amount.describe(),
                    "coefficient": float(component.coefficient),
                    "purity_required": (
                        float(component.purity_required)
                        if component.purity_required is not None
                        else None
                    ),
                    "note": component.note,
                }
                for component in recipe.components
            ],
        }

    @staticmethod
    def _issue(issue) -> Dict[str, Any]:
        return {
            "severity": issue.severity.value,
            "severity_label": issue.severity.label,
            "code": issue.code,
            "message": issue.message,
            "component_index": issue.component_index,
        }


# 模块级单例（页面直接引用；构造函数可注入，便于测试）
recipe_business_service = RecipeBusinessService()

__all__ = ["RecipeBusinessService", "recipe_business_service", "RECIPE_ROLES"]
