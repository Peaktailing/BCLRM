"""计量引擎：配方 + 规模 → 需求单。

解析分两轮，这是化学本身决定的，不是实现取巧：

1. **绝对量轮**：称了多少克、配了多少毫升、人均多少。这些不依赖别人。
2. **相对量轮**：几当量、基准的几倍体积、配成若干浓度。这些要等
   第一轮落地后才知道「以谁为 1.00」。

中间夹一步**限制试剂判定**：按「摩尔数 / 化学计量系数」取最小值，它
就是当量的基准（1.00 当量）。这一步让「按当量加料」不再靠人拍脑袋。

引擎不认识数据库，也不认识页面：物性通过 :class:`SubstanceResolver`
注入，管控状态通过参数传入。所有失败都以带行号的
:class:`MeteringError` 抛出——算不出来就不出单，绝不给一张漏料的清单。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from domain.amount import AmountError, ResolveContext
from domain.batch import BatchScale
from domain.recipe import (
    Recipe,
    RecipeComponent,
    RecipeError,
    ResolvedComponent,
)
from domain.requirement import RequirementLine, RequirementSheet
from domain.substance import ComponentRole, Substance, SubstanceRef
from domain.units import Quantity, UnitError


class MeteringError(RecipeError):
    """计量失败。带行号与原因，便于页面直接指到出错的那一行。"""

    def __init__(
        self,
        message: str,
        component_index: Optional[int] = None,
        substance: Optional[SubstanceRef] = None,
    ) -> None:
        self.component_index = component_index
        self.substance = substance
        prefix = f"第 {component_index + 1} 行" if component_index is not None else ""
        if prefix and substance is not None:
            prefix = f"{prefix}（{substance}）"
        super().__init__(f"{prefix}{message}" if prefix else message)


@dataclass(frozen=True)
class MeteringResult:
    """一次计量计算的完整产物。"""

    sheet: RequirementSheet
    basis_key: Optional[str] = None
    resolved: tuple[ResolvedComponent, ...] = ()

    @property
    def basis_component(self) -> Optional[ResolvedComponent]:
        if not self.basis_key:
            return None
        for item in self.resolved:
            if item.ref.key == self.basis_key:
                return item
        return None

    def explain(self) -> list[str]:
        """逐行推导（含产物行），报告与审计用。"""
        return [
            f"{index + 1}. {item.ref.name or item.ref.key}：{item.explanation}"
            for index, item in enumerate(self.resolved)
        ]


class MeteringEngine:
    """把配方算成需求单。无状态，可复用于任何场景。"""

    def __init__(self, resolver) -> None:
        # resolver 只需提供 get(ref)（见 domain.recipe.SubstanceCatalogLike）
        self._resolver = resolver

    # ---------------------------------------------------------------- 主流程
    def plan(
        self,
        recipe: Recipe,
        scale: Optional[BatchScale] = None,
        controlled_keys: Optional[Iterable[str]] = None,
        include_products: bool = False,
    ) -> MeteringResult:
        """计算需求单。

        Args:
            recipe: 配方聚合根
            scale: 备料规模（缺省单人单批）
            controlled_keys: 受管控物质引用键集合
            include_products: 产物是否进需求清单（默认不进，只作推导展示）

        Raises:
            MeteringError: 配方不自洽，或某行无法解析。
        """
        scale = scale or BatchScale.single()
        controlled = set(controlled_keys or ())

        report = recipe.validate()
        if not report.is_valid:
            detail = "；".join(str(issue) for issue in report.errors)
            raise MeteringError(f"配方校验未通过：{detail}")

        warnings = [f"{issue.severity.label}：{issue.message}" for issue in report.warnings]

        substances = self._load_substances(recipe)
        warnings.extend(self._property_warnings(recipe, substances))

        resolved: dict[str, Quantity] = {}
        records: list[ResolvedComponent] = []

        # ---- 第一轮：绝对量
        for index, component in enumerate(recipe.components):
            if component.depends_on_basis:
                continue
            quantity, explanation = self._resolve(component, index, scale, substances, resolved, None)
            resolved[component.substance.key] = quantity
            records.append(
                ResolvedComponent(component, quantity, explanation, substances.get(component.substance.key))
            )

        # ---- 限制试剂判定（当量的 1.00）
        basis_key = self._limiting_key(recipe, resolved, substances)

        # ---- 第二轮：相对量（按 seq 顺序，允许链式依赖前一行的解析结果）
        for index, component in enumerate(recipe.components):
            if not component.depends_on_basis:
                continue
            quantity, explanation = self._resolve(
                component, index, scale, substances, resolved, basis_key
            )
            resolved[component.substance.key] = quantity
            records.append(
                ResolvedComponent(component, quantity, explanation, substances.get(component.substance.key))
            )

        # ---- 汇总成需求行
        lines: list[RequirementLine] = []
        seq = 0
        for item in records:
            component = item.component
            if component.role is ComponentRole.PRODUCT:
                # 产物默认不备料；显式要求时才进清单（如需要标样比对）
                if not include_products:
                    continue
            elif not component.needs_material:
                continue
            lines.append(
                RequirementLine(
                    substance=component.substance,
                    role=component.role,
                    quantity=item.quantity,
                    basis_text=component.amount.describe(),
                    explanation=item.explanation,
                    purity_required=component.purity_required,
                    controlled=component.substance.key in controlled,
                    seq=seq,
                )
            )
            seq += 1

        if not lines:
            raise MeteringError("按当前配方与规模算出的需求为空，请检查组分角色与计量设置")

        sheet = RequirementSheet(
            recipe_key=recipe.key,
            title=recipe.title,
            scale=scale,
            lines=tuple(lines),
            source=recipe.source,
            warnings=tuple(dict.fromkeys(warnings)),
        )
        return MeteringResult(sheet=sheet, basis_key=basis_key, resolved=tuple(records))

    # ---------------------------------------------------------------- 内部
    def _load_substances(self, recipe: Recipe) -> dict[str, Substance]:
        """加载物性；缺物性时用「只有引用」的空壳兜底。

        空壳不是错误——库存里大量条目没有密度、甚至没有分子量。真到
        需要换算时才报错，报错信息会指明缺的是哪一项物性。
        """
        loaded: dict[str, Substance] = {}
        for component in recipe.components:
            found = None
            if self._resolver is not None:
                found = self._resolver.get(component.substance)
            loaded[component.substance.key] = found or Substance(component.substance)
        return loaded

    def _property_warnings(
        self, recipe: Recipe, substances: dict[str, Substance]
    ) -> list[str]:
        """提示缺物性的组分（会影响当量/浓度换算能力）。"""
        warnings: list[str] = []
        for component in recipe.components:
            substance = substances[component.substance.key]
            if substance.molar_mass is None and component.substance.formula is None:
                warnings.append(
                    f"提示：{component.label()} 没有分子量与分子式，无法按当量/物质的量换算"
                )
            elif substance.density is None and component.amount.requires_density():
                warnings.append(f"提示：{component.label()} 没有密度，体积与质量之间无法换算")
        return warnings

    def _resolve(
        self,
        component: RecipeComponent,
        index: int,
        scale: BatchScale,
        substances: dict[str, Substance],
        resolved: dict[str, Quantity],
        basis_key: Optional[str],
    ) -> tuple[Quantity, str]:
        substance = substances[component.substance.key]
        ctx = ResolveContext(
            scale=scale,
            substance=substance,
            resolved=resolved,
            substances=substances,
            basis_key=basis_key,
        )
        try:
            quantity = component.amount.resolve(ctx)
        except (AmountError, UnitError, ValueError) as exc:
            raise MeteringError(
                f"计量无法解析（{component.amount.describe()}）：{exc}",
                component_index=index,
                substance=component.substance,
            ) from exc
        if quantity.is_negative():
            raise MeteringError(
                f"算出了负数量（{quantity.format(3)}），请检查计量规则",
                component_index=index,
                substance=component.substance,
            )
        return quantity, component.amount.explain(ctx, quantity)

    def _limiting_key(
        self,
        recipe: Recipe,
        resolved: dict[str, Quantity],
        substances: dict[str, Substance],
    ) -> Optional[str]:
        """限制试剂：摩尔数 / 化学计量系数 最小者。

        只考虑已解析、且能折算出摩尔的反应物。若一个都算不出来（缺分子
        量），退回配方声明的第一个绝对量基准组分——这样至少还能算配比型
        的用量，而当量型会在解析时给出明确报错。
        """
        candidates: list[tuple[Decimal, int, str]] = []
        for order, component in enumerate(recipe.components):
            if not component.role.participates_in_stoichiometry:
                continue
            quantity = resolved.get(component.substance.key)
            if quantity is None:
                continue
            substance = substances.get(component.substance.key)
            if substance is None:
                continue
            try:
                moles = substance.moles_of(quantity)
            except UnitError:
                continue
            if component.coefficient <= 0:
                continue
            candidates.append((moles.value / component.coefficient, order, component.substance.key))

        if candidates:
            return min(candidates)[2]

        fallback = recipe.basis_component()
        return fallback.substance.key if fallback else None


__all__ = ["MeteringEngine", "MeteringError", "MeteringResult"]
