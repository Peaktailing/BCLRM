"""计量规则：把「配方上写的一行」翻译成「实际要多少」。

这是整个交叉模块的心脏。原有的做法是 ``qty_per_person × 人数`` 一条
路走到黑，遇到「按当量加」「配 0.1 mol/L 溶液」「溶剂按反应物的 10 倍
体积」就无处安放。这里用**多态**代替分支：每种计量方式是一个
:class:`AmountSpec` 子类，各自知道怎么解析、怎么描述、怎么落库。

新增一种计量方式 = 新增一个子类（会自动注册进反序列化表），不需要
回头改任何 ``if/elif``。这是「面向对象而非面向过程」最实在的落点。
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, ClassVar, Mapping, Optional

from domain.batch import BatchScale
from domain.substance import Substance
from domain.units import (
    MOL,
    Dimension,
    Quantity,
    Unit,
    UnitError,
    parse_unit,
)


class AmountError(ValueError):
    """计量规则无法解析（缺基准、缺体积、缺物性）。"""


# --------------------------------------------------------------------------
# 解析上下文
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolveContext:
    """解析一条计量的上下文。

    计量规则可能依赖别的东西：当量要问「以谁为 1.00」，配比要问「基准
    组分称了多少」，浓度要问「配到多少体积」。这些依赖全部通过上下文
    注入，规则自己不持有任何全局状态，因而可单独测试。

    Attributes:
        scale: 备料规模
        substance: 本行物质（提供分子量/密度/default_unit）
        resolved: 已解析的同伴数量，键为 :class:`SubstanceRef` 的 key
        substances: 同伴的物质信息，用于把质量折成摩尔
        basis_key: 当量基准的物质 key（通常为限制试剂）
    """

    scale: BatchScale
    substance: Substance
    resolved: Mapping[str, Quantity] = field(default_factory=dict)
    substances: Mapping[str, Substance] = field(default_factory=dict)
    basis_key: Optional[str] = None

    # ---------------------------------------------------------------- 取用
    def require_resolved(self, key: Optional[str], who: str) -> Quantity:
        if not key:
            raise AmountError(f"{who} 需要指定基准组分")
        quantity = self.resolved.get(key)
        if quantity is None:
            raise AmountError(f"{who} 的基准组分尚未解析: {key}")
        return quantity

    def require_substance(self, key: Optional[str], who: str) -> Substance:
        if not key:
            raise AmountError(f"{who} 需要指定基准组分")
        substance = self.substances.get(key)
        if substance is None:
            raise AmountError(f"{who} 的基准组分缺少物质信息: {key}")
        return substance

    def moles_of(self, key: str, who: str) -> Quantity:
        substance = self.require_substance(key, who)
        return substance.moles_of(self.require_resolved(key, who))

    def with_basis(self, basis_key: Optional[str]) -> "ResolveContext":
        return ResolveContext(
            scale=self.scale,
            substance=self.substance,
            resolved=self.resolved,
            substances=self.substances,
            basis_key=basis_key,
        )

    def with_resolved(self, key: str, quantity: Quantity) -> "ResolveContext":
        merged = dict(self.resolved)
        merged[key] = quantity
        return ResolveContext(
            scale=self.scale,
            substance=self.substance,
            resolved=merged,
            substances=self.substances,
            basis_key=self.basis_key,
        )


# --------------------------------------------------------------------------
# 抽象基类
# --------------------------------------------------------------------------


class AmountSpec(ABC):
    """一条计量规则。

    子类只需实现 :meth:`resolve` 与 :meth:`describe`，并提供类属性
    ``amount_type``；落库/回读由基类的模板方法统一处理。
    """

    #: 落库判别符，子类必须唯一
    amount_type: ClassVar[str] = ""
    #: 反序列化注册表（子类定义时自动登记）
    _registry: ClassVar[dict[str, type["AmountSpec"]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.amount_type:
            AmountSpec._registry[cls.amount_type] = cls

    # ---------------------------------------------------------------- 核心
    @abstractmethod
    def resolve(self, ctx: ResolveContext) -> Quantity:
        """算出本行实际需要的数量（单位尽量贴近使用习惯）。"""

    @abstractmethod
    def describe(self) -> str:
        """一句话说明这条规则（用于需求行的「依据」列）。"""

    def explain(self, ctx: ResolveContext, result: Quantity) -> str:
        """完整推导：规则 + 结果，便于在报告里交代「这个数怎么来的」。"""
        return f"{self.describe()} → {result.format(3)}"

    def requires_basis(self) -> bool:
        """是否依赖其他组分已解析（决定解析轮次）。"""
        return False

    def requires_density(self) -> bool:
        """跨量纲换算是否需要物质密度（决定缺物性提示）。"""
        return False

    def target_unit_hint(self) -> Optional[Unit]:
        """落在哪个单位上（None 表示由物质默认单位决定）。"""
        return None

    # ---------------------------------------------------------------- 序列化
    def _record_fields(self) -> dict:
        return {}

    def to_record(self) -> dict:
        """扁平记录，字段与 ``recipe_component`` 表列一一对应。"""
        record = {
            "amount_type": self.amount_type,
            "amount_value": None,
            "amount_unit": None,
            "ref_key": None,
            "concentration": None,
            "concentration_unit": None,
        }
        record.update(self._record_fields())
        return record

    @classmethod
    def from_record(cls, record: Optional[dict]) -> "AmountSpec":
        """按 ``amount_type`` 分派回具体规则。

        缺字段的存量数据（老库只有 qty_per_person）按人均处理，保证
        迁移期不炸。
        """
        record = record or {}
        kind = record.get("amount_type") or "per_person"
        spec_cls = cls._registry.get(kind)
        if spec_cls is None:
            raise AmountError(f"未知的计量方式: {kind!r}")
        return spec_cls._from_record(record)  # noqa: SLF001 - 模板方法

    @classmethod
    @abstractmethod
    def _from_record(cls, record: dict) -> "AmountSpec":
        """子类回读。"""

    # ---------------------------------------------------------------- 工具
    @staticmethod
    def _resolve_target_unit(ctx: ResolveContext, explicit: Optional[str]) -> Unit:
        if explicit:
            return parse_unit(explicit)
        return ctx.substance.default_unit

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} {self.describe()}>"


def _decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    if value in (None, ""):
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# --------------------------------------------------------------------------
# 1. 固定量：每次就这么多，不随规模放大
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedAmount(AmountSpec):
    """固定投料量。

    适用于「每批固定配 100 mL 指示液」「每釜加 5 g 干燥剂」这类与人数
    无关的量。注意它**只放大批次数**，不放大人数。
    """

    amount_type: ClassVar[str] = "fixed"

    quantity: Quantity

    def resolve(self, ctx: ResolveContext) -> Quantity:
        return self.quantity * Decimal(ctx.scale.batches)

    def describe(self) -> str:
        return f"每批固定 {self.quantity.format(3)}"

    def target_unit_hint(self) -> Optional[Unit]:
        return self.quantity.unit

    def _record_fields(self) -> dict:
        return {
            "amount_value": self.quantity.to_float(),
            "amount_unit": self.quantity.unit.symbol,
        }

    @classmethod
    def _from_record(cls, record: dict) -> "FixedAmount":
        unit = parse_unit(record.get("amount_unit"), default=parse_unit("g"))
        return cls(Quantity(_decimal(record.get("amount_value"), Decimal("0")), unit))


# --------------------------------------------------------------------------
# 2. 人均量：教学场景的主用法
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PerPersonAmount(AmountSpec):
    """人均用量 × 人数 × 批次。

    这是 BCLRM 原有的 ``experiment_default_usage.qty_per_person`` 语义，
    原样保留为一等公民，存量方案可直接映射过来。
    """

    amount_type: ClassVar[str] = "per_person"

    per_person: Quantity

    def resolve(self, ctx: ResolveContext) -> Quantity:
        return self.per_person * ctx.scale.multiplier

    def describe(self) -> str:
        return f"人均 {self.per_person.format(3)}"

    def explain(self, ctx: ResolveContext, result: Quantity) -> str:
        return (
            f"人均 {self.per_person.format(3)} × {ctx.scale.persons} 人"
            f" × {ctx.scale.batches} 批 = {result.format(3)}"
        )

    def target_unit_hint(self) -> Optional[Unit]:
        return self.per_person.unit

    def _record_fields(self) -> dict:
        return {
            "amount_value": self.per_person.to_float(),
            "amount_unit": self.per_person.unit.symbol,
        }

    @classmethod
    def _from_record(cls, record: dict) -> "PerPersonAmount":
        unit = parse_unit(record.get("amount_unit"), default=parse_unit("g"))
        return cls(Quantity(_decimal(record.get("amount_value"), Decimal("0")), unit))


# --------------------------------------------------------------------------
# 3. 每批量：科研场景的主用法
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PerBatchAmount(AmountSpec):
    """每批次用量 × 批次数（与人数无关）。"""

    amount_type: ClassVar[str] = "per_batch"

    per_batch: Quantity

    def resolve(self, ctx: ResolveContext) -> Quantity:
        return self.per_batch * Decimal(ctx.scale.batches)

    def describe(self) -> str:
        return f"每批 {self.per_batch.format(3)}"

    def explain(self, ctx: ResolveContext, result: Quantity) -> str:
        return f"每批 {self.per_batch.format(3)} × {ctx.scale.batches} 批 = {result.format(3)}"

    def target_unit_hint(self) -> Optional[Unit]:
        return self.per_batch.unit

    def _record_fields(self) -> dict:
        return {
            "amount_value": self.per_batch.to_float(),
            "amount_unit": self.per_batch.unit.symbol,
        }

    @classmethod
    def _from_record(cls, record: dict) -> "PerBatchAmount":
        unit = parse_unit(record.get("amount_unit"), default=parse_unit("g"))
        return cls(Quantity(_decimal(record.get("amount_value"), Decimal("0")), unit))


# --------------------------------------------------------------------------
# 4. 当量：以限制试剂为 1.00
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EquivalentsAmount(AmountSpec):
    """按当量投料：``摩尔数 = 基准组分摩尔数 × 当量``。

    基准组分默认取上下文里的 ``basis_key``（由计算引擎按限制试剂判定
    后注入），也可显式指定。结果单位优先用指定单位，否则用物质默认
    单位——若物质缺分子量而默认单位是质量，会给出明确的换算失败原因。
    """

    amount_type: ClassVar[str] = "equivalents"

    equivalents: Decimal
    basis_key: Optional[str] = None
    unit_symbol: Optional[str] = None

    def __post_init__(self) -> None:
        if self.equivalents <= 0:
            raise AmountError("当量必须为正")

    def requires_basis(self) -> bool:
        return True

    def resolve(self, ctx: ResolveContext) -> Quantity:
        basis_key = self.basis_key or ctx.basis_key
        basis_moles = ctx.moles_of(basis_key, "当量计量") if basis_key else None
        if basis_moles is None:
            raise AmountError(
                f"{ctx.substance} 按当量投料，但配方中没有可作为基准的绝对量反应物"
            )
        target_moles = basis_moles * self.equivalents
        target_unit = self._resolve_target_unit(ctx, self.unit_symbol)
        # 摩尔 → 目标单位可能要过分子量或密度，交给物质的换算能力
        return ctx.substance.convert(target_moles, target_unit)

    def describe(self) -> str:
        return f"{self.equivalents.normalize():f} 当量"

    def explain(self, ctx: ResolveContext, result: Quantity) -> str:
        basis_key = self.basis_key or ctx.basis_key
        try:
            basis_moles = ctx.moles_of(basis_key, "当量计量")
        except AmountError:
            return f"{self.describe()} → {result.format(3)}"
        return (
            f"基准 {basis_moles.format(4)} × {self.equivalents.normalize():f} 当量"
            f" = {result.format(3)}"
        )

    def target_unit_hint(self) -> Optional[Unit]:
        return parse_unit(self.unit_symbol) if self.unit_symbol else None

    def _record_fields(self) -> dict:
        return {
            "amount_value": float(self.equivalents),
            "amount_unit": self.unit_symbol,
            "ref_key": self.basis_key,
        }

    @classmethod
    def _from_record(cls, record: dict) -> "EquivalentsAmount":
        return cls(
            equivalents=_decimal(record.get("amount_value"), Decimal("1")),
            basis_key=record.get("ref_key") or None,
            unit_symbol=record.get("amount_unit") or None,
        )


# --------------------------------------------------------------------------
# 5. 配比：相对基准组分的份数
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RatioAmount(AmountSpec):
    """相对基准组分的份数（v/v、w/w、v/w 均可）。

    同量纲直接相乘；跨量纲用**本行物质的密度**过桥——溶剂按反应物
    质量的若干倍体积加入，是实验室最常见的写法之一。
    """

    amount_type: ClassVar[str] = "ratio"

    parts: Decimal
    basis_key: Optional[str] = None
    unit_symbol: Optional[str] = None

    def __post_init__(self) -> None:
        if self.parts <= 0:
            raise AmountError("配比份数必须为正")

    def requires_basis(self) -> bool:
        return True

    def requires_density(self) -> bool:
        # 跨量纲配比按「基准单位数值 × 份数」直接取值，不经过密度，
        # 因此不要求物质必须有密度。
        return False

    def resolve(self, ctx: ResolveContext) -> Quantity:
        basis_key = self.basis_key or ctx.basis_key
        basis_qty = ctx.require_resolved(basis_key, "配比计量")
        target_unit = self._resolve_target_unit(ctx, self.unit_symbol)

        if basis_qty.unit.dimension is target_unit.dimension:
            return basis_qty.to(target_unit) * self.parts

        # 跨量纲配比（如「溶剂取反应物质量的 3 倍体积」）：取基准量在
        # 其基准单位下的数值再乘份数，直接落到目标单位。
        # 24 g × 3 → 72 mL，而不是 24 g × 3 / 0.789 = 91 mL——后者是
        # 「按质量比折算体积」，不是实验室里「三倍体积」的意思。
        raw = basis_qty.base_value() * self.parts
        return Quantity(raw, target_unit)

    def describe(self) -> str:
        return f"基准组分的 {self.parts.normalize():f} 倍"

    def explain(self, ctx: ResolveContext, result: Quantity) -> str:
        return f"{self.describe()} → {result.format(3)}"

    def target_unit_hint(self) -> Optional[Unit]:
        return parse_unit(self.unit_symbol) if self.unit_symbol else None

    def _record_fields(self) -> dict:
        return {
            "amount_value": float(self.parts),
            "amount_unit": self.unit_symbol,
            "ref_key": self.basis_key,
        }

    @classmethod
    def _from_record(cls, record: dict) -> "RatioAmount":
        return cls(
            parts=_decimal(record.get("amount_value"), Decimal("1")),
            basis_key=record.get("ref_key") or None,
            unit_symbol=record.get("amount_unit") or None,
        )


# --------------------------------------------------------------------------
# 6. 浓度：配成指定浓度的溶液
# --------------------------------------------------------------------------

_CONCENTRATION = re.compile(r"^\s*(mol|mmol|μmol|umol|g|mg|μg|ug)\s*/\s*L\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ConcentrationAmount(AmountSpec):
    """配成指定浓度：``用量 = 浓度 × 目标体积``。

    目标体积取本行显式值，缺省取规模的容器体积。浓度单位支持
    ``mol/L``、``mmol/L``、``g/L``、``mg/L`` 等「某单位每升」写法。
    """

    amount_type: ClassVar[str] = "concentration"

    concentration: Decimal
    concentration_unit: str = "mol/L"
    target_volume: Optional[Quantity] = None
    unit_symbol: Optional[str] = None

    def __post_init__(self) -> None:
        if self.concentration < 0:
            raise AmountError("浓度不能为负")
        if not _CONCENTRATION.match(self.concentration_unit or ""):
            raise AmountError(f"无法识别的浓度单位: {self.concentration_unit!r}")

    def requires_density(self) -> bool:
        return True

    def _numerator_unit(self) -> Unit:
        match = _CONCENTRATION.match(self.concentration_unit)
        assert match is not None
        return parse_unit(match.group(1))

    def resolve(self, ctx: ResolveContext) -> Quantity:
        volume = self.target_volume or ctx.scale.vessel_volume
        if volume is None:
            raise AmountError(
                f"{ctx.substance} 按浓度计量，但未给出目标体积（请设置容器体积或本行体积）"
            )
        volume_l = volume.to("L").value
        total = Quantity(self.concentration * volume_l, self._numerator_unit())
        target_unit = self._resolve_target_unit(ctx, self.unit_symbol)
        return ctx.substance.convert(total, target_unit)

    def describe(self) -> str:
        volume = f"{self.target_volume.format(2)}" if self.target_volume else "容器体积"
        return f"配成 {self.concentration.normalize():f} {self.concentration_unit} × {volume}"

    def explain(self, ctx: ResolveContext, result: Quantity) -> str:
        volume = self.target_volume or ctx.scale.vessel_volume
        if volume is None:
            return f"{self.describe()} → {result.format(3)}"
        return (
            f"{self.concentration.normalize():f} {self.concentration_unit}"
            f" × {volume.format(2)} = {result.format(3)}"
        )

    def target_unit_hint(self) -> Optional[Unit]:
        return parse_unit(self.unit_symbol) if self.unit_symbol else None

    def _record_fields(self) -> dict:
        return {
            "concentration": float(self.concentration),
            "concentration_unit": self.concentration_unit,
            "amount_unit": self.unit_symbol,
            "amount_value": (
                self.target_volume.to_float() if self.target_volume is not None else None
            ),
        }

    @classmethod
    def _from_record(cls, record: dict) -> "ConcentrationAmount":
        volume = record.get("amount_value")
        return cls(
            concentration=_decimal(record.get("concentration"), Decimal("0")),
            concentration_unit=record.get("concentration_unit") or "mol/L",
            target_volume=(
                Quantity.of(volume, record.get("amount_unit") or "mL")
                if volume not in (None, "") and record.get("concentration_unit") is None
                else None
            ),
            unit_symbol=record.get("amount_unit") if record.get("concentration_unit") else None,
        )


# --------------------------------------------------------------------------
# 便捷构造
# --------------------------------------------------------------------------


def per_person(value: Any, unit: str = "g") -> PerPersonAmount:
    return PerPersonAmount(Quantity.of(value, unit))


def per_batch(value: Any, unit: str = "g") -> PerBatchAmount:
    return PerBatchAmount(Quantity.of(value, unit))


def fixed(value: Any, unit: str = "g") -> FixedAmount:
    return FixedAmount(Quantity.of(value, unit))


def equivalents(value: Any, basis_key: Optional[str] = None,
                unit_symbol: Optional[str] = None) -> EquivalentsAmount:
    return EquivalentsAmount(Decimal(str(value)), basis_key, unit_symbol)


def ratio(parts: Any, basis_key: Optional[str] = None,
          unit_symbol: Optional[str] = None) -> RatioAmount:
    return RatioAmount(Decimal(str(parts)), basis_key, unit_symbol)


def concentration(value: Any, unit: str = "mol/L",
                  target_volume: Optional[Quantity] = None,
                  unit_symbol: Optional[str] = None) -> ConcentrationAmount:
    return ConcentrationAmount(Decimal(str(value)), unit, target_volume, unit_symbol)


__all__ = [
    "AmountError",
    "ResolveContext",
    "AmountSpec",
    "FixedAmount",
    "PerPersonAmount",
    "PerBatchAmount",
    "EquivalentsAmount",
    "RatioAmount",
    "ConcentrationAmount",
    "per_person",
    "per_batch",
    "fixed",
    "equivalents",
    "ratio",
    "concentration",
]
