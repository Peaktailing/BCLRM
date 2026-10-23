"""计量单位与数量值对象。

设计要点（与既有 ``float + 字符串单位`` 的做法不同）：

1. **量纲（Dimension）先于单位**。质量、体积、物质的量、计数四个量纲
   互不换算；同一量纲内的单位才可互换。这样「3 g + 2 mL」在类型层面
   就写不出来，而不是等运行到某处才算出个错数。
2. **Quantity 是不可变值对象**。内部用 ``Decimal``，从 ``str(value)``
   构造，避免 ``0.1 + 0.2`` 这类二进制浮点误差；对外的
   ``to_float()`` 只在与 SQLite / 页面边界处使用。
3. **跨量纲换算不在这里做**。g ↔ mol 需要分子量，mL ↔ g 需要密度，
   那是物质自身的知识（见 :class:`domain.substance.Substance`），
   单位层只负责同一量纲内的缩放。

本模块不导入任何项目内其他模块，也不触碰数据库。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Optional


class UnitError(ValueError):
    """单位非法、量纲不匹配、数量非法时抛出。"""


class Dimension(str, Enum):
    """计量量纲。"""

    MASS = "mass"          # 质量：g / mg / kg / µg
    VOLUME = "volume"      # 体积：mL / L / µL
    AMOUNT = "amount"      # 物质的量：mol / mmol / µmol
    COUNT = "count"        # 计数：个 / 支 / 瓶
    PORTION = "portion"    # 份数（配比、当量等无量纲份额）

    @property
    def label(self) -> str:
        return {
            Dimension.MASS: "质量",
            Dimension.VOLUME: "体积",
            Dimension.AMOUNT: "物质的量",
            Dimension.COUNT: "计数",
            Dimension.PORTION: "份数",
        }[self]


@dataclass(frozen=True)
class Unit:
    """一个计量单位。

    ``to_base`` 表示「1 个本单位 = 多少个基准单位」，基准单位为
    g（质量）/ mL（体积）/ mol（物质的量）/ 个（计数）/ 份（份数）。
    """

    symbol: str
    dimension: Dimension
    to_base: Decimal

    def __post_init__(self) -> None:
        if not self.symbol:
            raise UnitError("单位符号不能为空")
        if self.to_base <= 0:
            raise UnitError(f"单位换算系数必须为正: {self.symbol}")

    def __str__(self) -> str:  # pragma: no cover - 仅便于调试
        return self.symbol


# --------------------------------------------------------------------------
# 预置单位表
# --------------------------------------------------------------------------

G = Unit("g", Dimension.MASS, Decimal("1"))
MG = Unit("mg", Dimension.MASS, Decimal("0.001"))
KG = Unit("kg", Dimension.MASS, Decimal("1000"))
UG = Unit("μg", Dimension.MASS, Decimal("0.000001"))

ML = Unit("mL", Dimension.VOLUME, Decimal("1"))
L = Unit("L", Dimension.VOLUME, Decimal("1000"))
UL = Unit("μL", Dimension.VOLUME, Decimal("0.001"))

MOL = Unit("mol", Dimension.AMOUNT, Decimal("1"))
MMOL = Unit("mmol", Dimension.AMOUNT, Decimal("0.001"))
UMOL = Unit("μmol", Dimension.AMOUNT, Decimal("0.000001"))

PIECE = Unit("个", Dimension.COUNT, Decimal("1"))
BOTTLE = Unit("瓶", Dimension.COUNT, Decimal("1"))
PORTION = Unit("份", Dimension.PORTION, Decimal("1"))

#: 所有可解析的单位。键为小写且把 µ/u 归一，便于容忍手输差异。
_UNIT_TABLE: dict[str, Unit] = {}


def _register(*units: Unit) -> None:
    for unit in units:
        _UNIT_TABLE[unit.symbol.lower()] = unit


_register(G, MG, KG, UG, ML, L, UL, MOL, MMOL, UMOL, PIECE, BOTTLE, PORTION)

# 常见别名（中文单位、大小写变体、微符号的两种写法）
_ALIASES: dict[str, str] = {
    "克": "g",
    "毫克": "mg",
    "千克": "kg",
    "公斤": "kg",
    "微克": "μg",
    "毫升": "ml",
    "升": "l",
    "微升": "μl",
    "摩尔": "mol",
    "毫摩尔": "mmol",
    "微摩尔": "μmol",
    "umol": "μmol",
    "ul": "μl",
    "ug": "μg",
    "n": "个",
    "支": "个",
    "只": "个",
}


def parse_unit(symbol: Optional[str], default: Optional[Unit] = None) -> Unit:
    """把用户输入的单位符号解析成 :class:`Unit`。

    Args:
        symbol: 单位符号，允许空（此时返回 ``default``）
        default: 符号为空时的兜底单位

    Raises:
        UnitError: 单位无法识别且未提供兜底
    """
    text = (symbol or "").strip()
    if not text:
        if default is not None:
            return default
        raise UnitError("单位为空")

    key = text.lower().replace("µ", "μ")
    key = _ALIASES.get(key, key)
    unit = _UNIT_TABLE.get(key)
    if unit is None:
        raise UnitError(f"无法识别的单位: {text!r}")
    return unit


def units_of(dimension: Dimension) -> list[Unit]:
    """某个量纲下所有预置单位（用于页面下拉）。"""
    return [u for u in _UNIT_TABLE.values() if u.dimension == dimension]


# --------------------------------------------------------------------------
# 数量值对象
# --------------------------------------------------------------------------

_ZERO_TOLERANCE = Decimal("1e-12")


def _as_decimal(value: Any) -> Decimal:
    """把外部数值安全地转为 Decimal。

    ``float`` 走 ``str()`` 中转，避免 ``Decimal(0.1)`` 得到
    0.1000000000000000055511151231257827 这种二进制残影。
    """
    if isinstance(value, bool):
        raise UnitError("布尔值不是合法数量")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, float):
        result = Decimal(str(value))
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation as exc:
            raise UnitError(f"不是合法数值: {value!r}") from exc
    else:
        raise UnitError(f"不支持的数量类型: {type(value).__name__}")

    if not result.is_finite():
        raise UnitError(f"数量必须有限: {value!r}")
    return result


@dataclass(frozen=True)
class Quantity:
    """带单位的数量（不可变）。

    >>> Quantity.of("1.5", "g").to(MG)
    Quantity(value=Decimal('1500.0'), unit=Unit(symbol='mg', ...))
    """

    value: Decimal
    unit: Unit

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            object.__setattr__(self, "value", _as_decimal(self.value))
        if self.value.is_nan():  # 防御：Decimal 构造后仍可能被外部塞 NaN
            raise UnitError("数量不能是 NaN")

    # ---------------------------------------------------------------- 构造
    @classmethod
    def of(cls, value: Any, unit: Any) -> "Quantity":
        """便捷构造：``Quantity.of(1.5, "g")``。"""
        return cls(_as_decimal(value), unit if isinstance(unit, Unit) else parse_unit(unit))

    @classmethod
    def zero(cls, unit: Unit) -> "Quantity":
        return cls(Decimal("0"), unit)

    # ------------------------------------------------------------ 同量纲换算
    def to(self, unit: Any) -> "Quantity":
        """换算到同量纲的另一个单位。"""
        target = unit if isinstance(unit, Unit) else parse_unit(unit)
        if target.dimension is not self.unit.dimension:
            raise UnitError(
                f"{self.unit.dimension.label} 与 {target.dimension.label} 不能互换"
            )
        if target == self.unit:
            return self
        return Quantity(self.value * self.unit.to_base / target.to_base, target)

    def base_value(self) -> Decimal:
        """换算到基准单位后的数值（用于跨单位比较/汇总）。"""
        return self.value * self.unit.to_base

    @classmethod
    def from_base(cls, value: Any, unit: Unit) -> "Quantity":
        return cls(_as_decimal(value) / unit.to_base, unit)

    # ---------------------------------------------------------------- 运算
    def _require_same_dimension(self, other: "Quantity", op: str) -> None:
        if not isinstance(other, Quantity):
            raise UnitError(f"{op} 需要 Quantity，收到 {type(other).__name__}")
        if other.unit.dimension is not self.unit.dimension:
            raise UnitError(
                f"{self.unit.dimension.label} 与 {other.unit.dimension.label} 不能{op}"
            )

    def __add__(self, other: "Quantity") -> "Quantity":
        self._require_same_dimension(other, "相加")
        return Quantity(self.value + other.to(self.unit).value, self.unit)

    def __sub__(self, other: "Quantity") -> "Quantity":
        self._require_same_dimension(other, "相减")
        return Quantity(self.value - other.to(self.unit).value, self.unit)

    def __mul__(self, factor: Any) -> "Quantity":
        return Quantity(self.value * _as_decimal(factor), self.unit)

    __rmul__ = __mul__

    def __truediv__(self, other: Any) -> Any:
        """除以标量得数量；除以同量纲数量得无量纲比值。"""
        if isinstance(other, Quantity):
            self._require_same_dimension(other, "相除")
            denominator = other.to(self.unit).value
            if denominator == 0:
                raise UnitError("除数为零")
            return self.value / denominator
        factor = _as_decimal(other)
        if factor == 0:
            raise UnitError("除数为零")
        return Quantity(self.value / factor, self.unit)

    def __neg__(self) -> "Quantity":
        return Quantity(-self.value, self.unit)

    # ---------------------------------------------------------------- 判定
    def is_zero(self, tolerance: Decimal = _ZERO_TOLERANCE) -> bool:
        return abs(self.value) <= tolerance

    def is_positive(self) -> bool:
        return self.value > 0

    def is_negative(self) -> bool:
        return self.value < 0

    def clamp_non_negative(self) -> "Quantity":
        return Quantity(Decimal("0"), self.unit) if self.value < 0 else self

    def __lt__(self, other: "Quantity") -> bool:
        self._require_same_dimension(other, "比较")
        return self.value < other.to(self.unit).value

    def __le__(self, other: "Quantity") -> bool:
        self._require_same_dimension(other, "比较")
        return self.value <= other.to(self.unit).value

    def __gt__(self, other: "Quantity") -> bool:
        self._require_same_dimension(other, "比较")
        return self.value > other.to(self.unit).value

    def __ge__(self, other: "Quantity") -> bool:
        self._require_same_dimension(other, "比较")
        return self.value >= other.to(self.unit).value

    # ---------------------------------------------------------------- 输出
    def rounded(self, places: int = 4) -> "Quantity":
        """按小数位四舍五入（**只用于展示与落库**，中间计算保留全精度）。"""
        quantum = Decimal(1).scaleb(-places)
        return Quantity(self.value.quantize(quantum), self.unit)

    def to_float(self) -> float:
        return float(self.value)

    def format(self, places: int = 2) -> str:
        """按有效展示格式输出，整数不带小数点。"""
        value = self.rounded(places).value
        if value == value.to_integral_value():
            text = str(int(value))
        else:
            text = f"{value:.{places}f}".rstrip("0").rstrip(".")
        return f"{text} {self.unit.symbol}"

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:  # pragma: no cover
        return f"Quantity({self.value}, {self.unit.symbol!r})"


def total(quantities: Iterable[Quantity], unit: Unit) -> Quantity:
    """同量纲数量求和，统一到 ``unit``。

    空序列返回该单位的零值——汇总场景（库存合计）需要这个语义，
    而不是抛异常。
    """
    result = Quantity.zero(unit)
    for item in quantities:
        result = result + item.to(unit)
    return result


__all__ = [
    "Dimension",
    "Unit",
    "UnitError",
    "Quantity",
    "parse_unit",
    "units_of",
    "total",
    "G", "MG", "KG", "UG",
    "ML", "L", "UL",
    "MOL", "MMOL", "UMOL",
    "PIECE", "BOTTLE", "PORTION",
]
