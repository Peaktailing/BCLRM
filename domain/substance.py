"""物质（Substance）与它的稳定引用。

这是两条纵线的**公共语言**：库存说「这瓶是 64-19-7」，配方说「我要
64-19-7 3 mL」，采购说「补 64-19-7 500 mL」。三者必须指同一个东西，
所以引入 :class:`SubstanceRef` 作为跨模块的物质标识，而不是各层各写
一个 ``reagent_name`` 字符串去互相碰运气。

引用优先级：CAS > 分子式 > 规范名。CAS 是化学世界的唯一键；没有 CAS
时退到 Hill 式；再退到规范化名称（去空白、统一大小写与全半角）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional

from domain.chemistry import CasNumber, FormulaError, MolecularFormula
from domain.units import (
    Dimension,
    Quantity,
    Unit,
    UnitError,
    parse_unit,
)


class ConversionError(UnitError):
    """跨量纲换算失败（缺分子量或密度）。"""


class ComponentRole(str, Enum):
    """组分在配方中的角色。

    角色决定三件事：是否参与当量基准、是否默认产生物料需求、是否受
    管控名录约束。把这些判断收敛到枚举上，业务代码里就不会再出现
    ``if role == "溶剂"`` 这类散落的字符串比较。
    """

    REACTANT = "reactant"      # 反应物：参与化学计量
    REAGENT = "reagent"        # 试剂/辅助试剂：常按当量或用量给
    SOLVENT = "solvent"        # 溶剂：按体积或配比给，不参与计量
    CATALYST = "catalyst"      # 催化剂：微量，通常按当量
    INDICATOR = "indicator"    # 指示剂：微量
    CONSUMABLE = "consumable"  # 耗材（滤纸、硅胶等）：非化学品
    PRODUCT = "product"        # 产物：默认不产生物料需求

    @property
    def label(self) -> str:
        return {
            ComponentRole.REACTANT: "反应物",
            ComponentRole.REAGENT: "试剂",
            ComponentRole.SOLVENT: "溶剂",
            ComponentRole.CATALYST: "催化剂",
            ComponentRole.INDICATOR: "指示剂",
            ComponentRole.CONSUMABLE: "耗材",
            ComponentRole.PRODUCT: "产物",
        }[self]

    @property
    def participates_in_stoichiometry(self) -> bool:
        """是否参与当量/限制试剂计算。溶剂与指示剂不参与。"""
        return self in (
            ComponentRole.REACTANT,
            ComponentRole.REAGENT,
            ComponentRole.CATALYST,
        )

    @property
    def needs_material(self) -> bool:
        """是否默认要备料。产物默认不备料（要备也应由调用方显式声明）。"""
        return self is not ComponentRole.PRODUCT


_WHITESPACE = re.compile(r"\s+")
_FULLWIDTH_OFFSET = 0xFEE0


def normalize_name(name: Optional[str]) -> str:
    """名称规范化：全角转半角、去空白、统一小写。

    只做「同一个名字的不同写法归一」，不做同义词归并——同义词属化学
    品信息维护的职责，混进这里会让匹配变得不可预期。
    """
    text = (name or "").strip()
    if not text:
        return ""
    text = "".join(
        chr(ord(ch) - _FULLWIDTH_OFFSET) if 0xFF01 <= ord(ch) <= 0xFF5E else ch
        for ch in text
    )
    text = text.replace("\u3000", " ")
    return _WHITESPACE.sub("", text).lower()


@dataclass(frozen=True)
class SubstanceRef:
    """物质的稳定引用（不可变值对象，可作字典键）。"""

    #: 规范化引用键，形如 ``cas:64-19-7`` / ``formula:C2H4O2`` / ``name:乙酸``
    key: str
    name: str
    cas: Optional[CasNumber] = None
    formula: Optional[MolecularFormula] = None

    # ---------------------------------------------------------------- 构造
    @classmethod
    def of(
        cls,
        name: str,
        cas: Optional[str] = None,
        formula: Optional[str] = None,
    ) -> "SubstanceRef":
        """按 CAS > 分子式 > 名称 的优先级建立引用。"""
        cas_obj = CasNumber.try_parse(cas)
        formula_obj = MolecularFormula.try_parse(formula)
        display = (name or "").strip()

        if cas_obj is not None:
            key = f"cas:{cas_obj.value}"
        elif formula_obj is not None:
            key = f"formula:{formula_obj.hill_text()}"
        else:
            normalized = normalize_name(display)
            if not normalized:
                raise ValueError("建立物质引用至少需要名称、CAS 或分子式之一")
            key = f"name:{normalized}"
        return cls(key=key, name=display, cas=cas_obj, formula=formula_obj)

    @classmethod
    def from_key(cls, key: str) -> "SubstanceRef":
        """从引用键还原（只带键，名称留空，用于查询占位）。"""
        return cls(key=key, name="")

    # ---------------------------------------------------------------- 判定
    def matches(self, other: "SubstanceRef") -> bool:
        """两个引用是否指向同一物质。

        规则：引用键相等即同一；否则凡双方都有 CAS 且相等即同一；否则
        凡双方都有分子式且元素组成相同即同一。名称不参与跨键比对——
        重名不同物在化学试剂里太常见。
        """
        if self.key == other.key:
            return True
        if self.cas is not None and other.cas is not None:
            return self.cas.value == other.cas.value
        if self.formula is not None and other.formula is not None:
            return self.formula.is_balanced(other.formula)
        return False

    def with_name(self, name: str) -> "SubstanceRef":
        """补上显示名（仓储批量补名时用）。"""
        return SubstanceRef(self.key, name, self.cas, self.formula)

    def __str__(self) -> str:
        if self.name:
            return self.name
        if self.cas is not None:
            return self.cas.value
        return self.key


@dataclass(frozen=True)
class Substance:
    """一种物质的领域表示：引用 + 可用于换算的物性。

    ``molar_mass`` / ``density`` 允许为空——真实库存里总有没录物性的
    条目。缺物性时换算会明确报错，而不是悄悄按 1:1 处理。
    """

    ref: SubstanceRef
    molar_mass: Optional[Decimal] = None          # g/mol
    density: Optional[Decimal] = None             # g/mL（液体）
    purity: Optional[Decimal] = None              # 0~1
    controlled: bool = False                      # 是否在管控名录
    hazard_types: tuple[str, ...] = ()
    default_unit: Unit = field(default=None)      # 库存默认计量单位

    def __post_init__(self) -> None:
        if self.default_unit is None:
            object.__setattr__(self, "default_unit", parse_unit("g"))
        if self.molar_mass is not None and self.molar_mass <= 0:
            raise ValueError("摩尔质量必须为正")
        if self.density is not None and self.density <= 0:
            raise ValueError("密度必须为正")

    # ---------------------------------------------------------------- 构造
    @classmethod
    def of(
        cls,
        name: str,
        cas: Optional[str] = None,
        formula: Optional[str] = None,
        molar_mass: Optional[float] = None,
        density: Optional[float] = None,
        purity: Optional[float] = None,
        controlled: bool = False,
        hazard_types: tuple[str, ...] = (),
        default_unit: Optional[str] = None,
    ) -> "Substance":
        ref = SubstanceRef.of(name, cas, formula)
        # 有分子式但没给分子量时，自行推算——这正是「按式算量」的价值
        mw = Decimal(str(molar_mass)) if molar_mass is not None else None
        if mw is None and ref.formula is not None:
            mw = ref.formula.molar_mass
        return cls(
            ref=ref,
            molar_mass=mw,
            density=Decimal(str(density)) if density is not None else None,
            purity=Decimal(str(purity)) if purity is not None else None,
            controlled=controlled,
            hazard_types=tuple(hazard_types),
            default_unit=parse_unit(default_unit, default=parse_unit("g")),
        )

    # ---------------------------------------------------------------- 换算
    @property
    def can_interconvert_mass_amount(self) -> bool:
        return self.molar_mass is not None

    @property
    def can_interconvert_mass_volume(self) -> bool:
        return self.density is not None

    def convert(self, quantity: Quantity, target: Unit) -> Quantity:
        """把数量换算到目标单位，必要时经分子量或密度过桥。

        Raises:
            ConversionError: 目标量纲需要缺失的物性。
        """
        source = quantity.unit
        if source.dimension is target.dimension:
            return quantity.to(target)

        base = quantity.base_value()

        if source.dimension is Dimension.MASS:
            grams = base
            if target.dimension is Dimension.AMOUNT:
                if self.molar_mass is None:
                    raise ConversionError(
                        f"{self.ref} 缺少分子量，无法把质量换算为物质的量"
                    )
                return Quantity(grams / self.molar_mass, target).to(target)
            if target.dimension is Dimension.VOLUME:
                if self.density is None:
                    raise ConversionError(
                        f"{self.ref} 缺少密度，无法把质量换算为体积"
                    )
                return Quantity(grams / self.density, target).to(target)
        elif source.dimension is Dimension.AMOUNT:
            moles = base
            if target.dimension is Dimension.MASS:
                if self.molar_mass is None:
                    raise ConversionError(
                        f"{self.ref} 缺少分子量，无法把物质的量换算为质量"
                    )
                return Quantity(moles * self.molar_mass, target).to(target)
        elif source.dimension is Dimension.VOLUME:
            milliliters = base
            if target.dimension is Dimension.MASS:
                if self.density is None:
                    raise ConversionError(
                        f"{self.ref} 缺少密度，无法把体积换算为质量"
                    )
                return Quantity(milliliters * self.density, target).to(target)
            if target.dimension is Dimension.AMOUNT:
                if self.density is None or self.molar_mass is None:
                    raise ConversionError(
                        f"{self.ref} 缺少密度或分子量，无法把体积换算为物质的量"
                    )
                grams = milliliters * self.density
                return Quantity(grams / self.molar_mass, target).to(target)

        raise ConversionError(
            f"{source.dimension.label} 无法换算为 {target.dimension.label}"
        )

    def moles_of(self, quantity: Quantity) -> Quantity:
        """折算成 mol（缺分子量则报错）。"""
        return self.convert(quantity, parse_unit("mol"))

    def mass_of(self, quantity: Quantity) -> Quantity:
        """折算成 g。"""
        return self.convert(quantity, parse_unit("g"))

    def volume_of(self, quantity: Quantity) -> Quantity:
        """折算成 mL（缺密度则报错）。"""
        return self.convert(quantity, parse_unit("mL"))

    # ---------------------------------------------------------------- 判定
    def is_pure_enough(self, required: Optional[Decimal]) -> bool:
        """纯度是否满足配方要求。未录纯度视为「未声明」，按满足处理。"""
        if required is None or self.purity is None:
            return True
        return self.purity >= required

    def hazard_summary(self) -> str:
        return "、".join(self.hazard_types) if self.hazard_types else ""

    def __str__(self) -> str:
        return str(self.ref) or self.ref.key


class SubstanceCatalog:
    """内存物质目录：按引用键索引，供计算期快速取物性。

    它不是仓储（不落库），只是中台在一次计算里用的只读快照；持久化
    的物质主数据仍由 ``services/chemical_service.py`` 负责。
    """

    def __init__(self, substances: Optional[list[Substance]] = None) -> None:
        self._by_key: dict[str, Substance] = {}
        # 同一物质可能以 CAS 建引用、也可能以名称建引用，这里保留
        # 多键投影，让两种写法都能命中同一份物性。
        self._aliases: dict[str, str] = {}
        for item in substances or []:
            self.add(item)

    def add(self, substance: Substance) -> None:
        key = substance.ref.key
        self._by_key[key] = substance
        self._aliases.setdefault(key, key)
        if substance.ref.cas is not None:
            self._aliases.setdefault(f"cas:{substance.ref.cas.value}", key)
        if substance.ref.formula is not None:
            self._aliases.setdefault(f"formula:{substance.ref.formula.hill_text()}", key)
        if substance.ref.name:
            self._aliases.setdefault(f"name:{normalize_name(substance.ref.name)}", key)

    def get(self, ref: SubstanceRef) -> Optional[Substance]:
        if ref.key in self._by_key:
            return self._by_key[ref.key]
        alias = self._aliases.get(ref.key)
        if alias:
            return self._by_key.get(alias)
        # 最后兜底：线性比对 CAS / 分子式（目录通常几十到几百条，可接受）
        for substance in self._by_key.values():
            if substance.ref.matches(ref):
                return substance
        return None

    def require(self, ref: SubstanceRef) -> Substance:
        found = self.get(ref)
        if found is None:
            raise LookupError(f"物质目录中缺少 {ref}")
        return found

    def __len__(self) -> int:
        return len(self._by_key)

    def __contains__(self, ref: object) -> bool:
        return isinstance(ref, SubstanceRef) and self.get(ref) is not None


def count_by_role(substances: Mapping[ComponentRole, list[Substance]]) -> dict[str, int]:
    """按角色统计（页面摘要用）。"""
    return {role.value: len(items) for role, items in substances.items()}


__all__ = [
    "ComponentRole",
    "ConversionError",
    "SubstanceRef",
    "Substance",
    "SubstanceCatalog",
    "normalize_name",
    "count_by_role",
]
