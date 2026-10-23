"""化学值对象：分子式与 CAS 号。

原先 ``biomanager`` 的 chemlib 是一组纯函数（``parse_formula`` /
``molecular_weight``），调用方拿字符串到处传。这里把它们收成两个
不可变值对象，让「分子式知道自己有多重」「CAS 号知道自己是否合法」
成为对象的能力，而不是一堆散落的过程调用。

保留的能力：

- 结晶水（``CuSO4·5H2O`` / ``Na2CO3.10H2O``）
- 括号基团（``(NH4)2SO4``）
- 非整比（``Fe0.5O``）
- CAS 校验位（``7732-18-5``）

未知元素一律抛 :class:`FormulaError`，绝不猜——一个猜出来的分子量会
一路污染当量与投料量，比报错危险得多。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping, Optional

#: IUPAC 标准原子量（2021），收录实验室常见元素。
ATOMIC_WEIGHTS: dict[str, Decimal] = {
    "H": Decimal("1.008"), "He": Decimal("4.0026"), "Li": Decimal("6.94"),
    "Be": Decimal("9.0122"), "B": Decimal("10.81"), "C": Decimal("12.011"),
    "N": Decimal("14.007"), "O": Decimal("15.999"), "F": Decimal("18.998"),
    "Ne": Decimal("20.180"), "Na": Decimal("22.990"), "Mg": Decimal("24.305"),
    "Al": Decimal("26.982"), "Si": Decimal("28.085"), "P": Decimal("30.974"),
    "S": Decimal("32.06"), "Cl": Decimal("35.45"), "Ar": Decimal("39.948"),
    "K": Decimal("39.098"), "Ca": Decimal("40.078"), "Sc": Decimal("44.956"),
    "Ti": Decimal("47.867"), "V": Decimal("50.942"), "Cr": Decimal("51.996"),
    "Mn": Decimal("54.938"), "Fe": Decimal("55.845"), "Co": Decimal("58.933"),
    "Ni": Decimal("58.693"), "Cu": Decimal("63.546"), "Zn": Decimal("65.38"),
    "Ga": Decimal("69.723"), "Ge": Decimal("72.630"), "As": Decimal("74.922"),
    "Se": Decimal("78.971"), "Br": Decimal("79.904"), "Kr": Decimal("83.798"),
    "Rb": Decimal("85.468"), "Sr": Decimal("87.62"), "Y": Decimal("88.906"),
    "Zr": Decimal("91.224"), "Nb": Decimal("92.906"), "Mo": Decimal("95.95"),
    "Tc": Decimal("97.0"), "Ru": Decimal("101.07"), "Rh": Decimal("102.91"),
    "Pd": Decimal("106.42"), "Ag": Decimal("107.87"), "Cd": Decimal("112.41"),
    "In": Decimal("114.82"), "Sn": Decimal("118.71"), "Sb": Decimal("121.76"),
    "Te": Decimal("127.60"), "I": Decimal("126.90"), "Xe": Decimal("131.29"),
    "Cs": Decimal("132.91"), "Ba": Decimal("137.33"), "La": Decimal("138.91"),
    "Ce": Decimal("140.12"), "Pr": Decimal("140.91"), "Nd": Decimal("144.24"),
    "Sm": Decimal("150.36"), "Eu": Decimal("151.96"), "Gd": Decimal("157.25"),
    "Tb": Decimal("158.93"), "Dy": Decimal("162.50"), "Ho": Decimal("164.93"),
    "Er": Decimal("167.26"), "Yb": Decimal("173.05"), "Lu": Decimal("174.97"),
    "Hf": Decimal("178.49"), "Ta": Decimal("180.95"), "W": Decimal("183.84"),
    "Re": Decimal("186.21"), "Os": Decimal("190.23"), "Ir": Decimal("192.22"),
    "Pt": Decimal("195.08"), "Au": Decimal("196.97"), "Hg": Decimal("200.59"),
    "Tl": Decimal("204.38"), "Pb": Decimal("207.2"), "Bi": Decimal("208.98"),
    "Th": Decimal("232.04"), "U": Decimal("238.03"),
}


class FormulaError(ValueError):
    """分子式读不出来：未知元素、括号不配对、空式。"""


class CasError(ValueError):
    """CAS 号格式非法或校验位不符。"""


_ELEMENT = re.compile(r"([A-Z][a-z]?)(\d*(?:\.\d+)?)")
_HYDRATE_SPLIT = re.compile(r"[·•]")
_LEADING_COUNT = re.compile(r"^(\d+(?:\.\d+)?)(.*)$")
_TRAILING_COUNT = re.compile(r"^(\d+(?:\.\d+)?)")


def _read_unit(formula: str) -> dict[str, Decimal]:
    """读一个化学式单元（不含结晶水点）。"""
    if "·" in formula or "•" in formula:
        raise FormulaError(f"结晶水点不属于单个单元: {formula!r}")

    counts: dict[str, Decimal] = {}

    def add_group(group: str, multiplier: Decimal) -> None:
        pos = 0
        for match in _ELEMENT.finditer(group):
            if match.start() != pos:
                raise FormulaError(f"无法解析 {formula!r} 的 {group[pos:match.start()]!r}")
            symbol, count = match.group(1), match.group(2)
            if symbol not in ATOMIC_WEIGHTS:
                raise FormulaError(f"{symbol!r} 不是已知元素（出现在 {formula!r}）")
            amount = Decimal(count) if count else Decimal("1")
            counts[symbol] = counts.get(symbol, Decimal("0")) + amount * multiplier
            pos = match.end()
        if pos != len(group):
            raise FormulaError(f"无法解析 {formula!r} 的 {group[pos:]!r}")

    def add_part(part: str) -> None:
        part = part.strip()
        if not part:
            raise FormulaError(f"{formula!r} 中存在空片段")
        lead = _LEADING_COUNT.match(part)
        multiplier = Decimal(lead.group(1)) if lead else Decimal("1")
        body = lead.group(2) if lead else part

        depth = 0
        start = 0
        plain: list[str] = []
        for i, ch in enumerate(body):
            if ch == "(":
                if depth == 0:
                    plain.append(body[start:i])
                    start = i + 1
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    raise FormulaError(f"括号不配对: {formula!r}")
                if depth == 0:
                    inner = body[start:i]
                    after = _TRAILING_COUNT.match(body[i + 1:])
                    times = Decimal(after.group(1)) if after else Decimal("1")
                    add_group(inner, times)
                    start = i + 1 + (len(after.group(1)) if after else 0)
        if depth != 0:
            raise FormulaError(f"括号不配对: {formula!r}")
        plain.append(body[start:])
        for chunk in plain:
            if chunk.strip():
                add_group(chunk, multiplier)

    add_part(formula)
    return counts


def _read_one(formula: str) -> dict[str, Decimal]:
    """读整体化学式，处理结晶水点。

    只有点号两侧都能读成「完整且每种元素计数为正」的单元时，才按结晶水
    拆分；否则点号是小数点（``Fe0.5O``）。
    """
    text = (formula or "").strip()
    if not text:
        raise FormulaError("分子式为空")

    if "·" in text or "•" in text:
        counts: dict[str, Decimal] = {}
        for part in _HYDRATE_SPLIT.split(text):
            for symbol, n in _read_unit(part).items():
                counts[symbol] = counts.get(symbol, Decimal("0")) + n
        return counts

    for i, ch in enumerate(text):
        if ch != ".":
            continue
        try:
            left, right = _read_unit(text[:i]), _read_unit(text[i + 1:])
        except FormulaError:
            continue
        if _all_positive(left) and _all_positive(right):
            merged = dict(left)
            for symbol, n in right.items():
                merged[symbol] = merged.get(symbol, Decimal("0")) + n
            return merged
    return _read_unit(text)


def _all_positive(counts: Mapping[str, Decimal]) -> bool:
    return bool(counts) and all(n > 0 for n in counts.values())


@dataclass(frozen=True)
class MolecularFormula:
    """分子式（不可变值对象）。

    构造时即完成解析与分子量计算，之后的 ``molar_mass`` 只是读字段，
    不存在「同一个式子在不同地方算出不同重量」的可能。
    """

    text: str
    #: ((元素符号, 原子计数), ...)，按输入顺序，便于复现原始写法
    _counts: tuple[tuple[str, Decimal], ...]

    # ---------------------------------------------------------------- 构造
    @classmethod
    def parse(cls, text: str) -> "MolecularFormula":
        """解析分子式字符串。

        >>> MolecularFormula.parse("C6H12O6").molar_mass
        Decimal('180.156')
        >>> MolecularFormula.parse("CuSO4·5H2O").molar_mass
        Decimal('249.685')
        """
        counts = _read_one(text)
        return cls((text or "").strip(), tuple(counts.items()))

    @classmethod
    def try_parse(cls, text: Optional[str]) -> Optional["MolecularFormula"]:
        """宽松解析：读不出来返回 ``None``。

        用于「用户填了式子但不是系统能算的」这种数据清洗场景，
        与 ``parse`` 的失败即报错形成分工。
        """
        if not text or not str(text).strip():
            return None
        try:
            return cls.parse(str(text))
        except FormulaError:
            return None

    # ---------------------------------------------------------------- 属性
    @property
    def composition(self) -> dict[str, Decimal]:
        """元素计数快照。"""
        return dict(self._counts)

    @property
    def elements(self) -> tuple[str, ...]:
        return tuple(symbol for symbol, _ in self._counts)

    @property
    def molar_mass(self) -> Decimal:
        """摩尔质量，g/mol。

        刻意不做四舍五入：中间计算保留全精度，展示层再舍入。
        """
        return sum(
            (ATOMIC_WEIGHTS[symbol] * count for symbol, count in self._counts),
            Decimal("0"),
        )

    def mass_fraction(self, symbol: str) -> Decimal:
        """某元素的质量分数（0~1），用于纯度/元素衡算。"""
        total = self.molar_mass
        if total <= 0:
            return Decimal("0")
        part = ATOMIC_WEIGHTS.get(symbol)
        if part is None:
            raise FormulaError(f"{symbol!r} 不是已知元素")
        count = dict(self._counts).get(symbol, Decimal("0"))
        return part * count / total

    def hill_text(self) -> str:
        """按 Hill 次序输出（C、H 在前，其余字母序），产物登记时用。"""
        parts: list[str] = []
        for symbol in sorted(self._counts_key(), key=lambda s: (s != "C", s != "H", s)):
            count = dict(self._counts)[symbol]
            if count == int(count):
                text = str(int(count))
            else:
                text = f"{count.normalize():f}".rstrip("0").rstrip(".")
            parts.append(symbol + ("" if count == 1 else text))
        return "".join(parts)

    def _counts_key(self) -> list[str]:
        return [symbol for symbol, _ in self._counts]

    # ---------------------------------------------------------------- 判定
    def is_balanced(self, other: "MolecularFormula") -> bool:
        """两个式子元素组成是否完全相同（互变异构/同分异构不算）。"""
        left = {symbol: count for symbol, count in self._counts if count != 0}
        right = {symbol: count for symbol, count in other._counts if count != 0}
        return left == right

    def __str__(self) -> str:
        return self.text or self.hill_text()


def combine_formulas(*formulas: MolecularFormula) -> MolecularFormula:
    """多个式子的加和（用于配平校验的左右两侧汇总）。"""
    merged: dict[str, Decimal] = {}
    for formula in formulas:
        for symbol, count in formula._counts:
            merged[symbol] = merged.get(symbol, Decimal("0")) + count
    text = "·".join(formula.text for formula in formulas if formula.text)
    return MolecularFormula(text, tuple(merged.items()))


def element_counts_to_formula(counts: Mapping[str, Decimal]) -> MolecularFormula:
    """元素计数 → 分子式（产物登记的逆操作）。"""
    return MolecularFormula("", tuple(counts.items()))


# --------------------------------------------------------------------------
# CAS 号
# --------------------------------------------------------------------------

_CAS_PATTERN = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")


@dataclass(frozen=True)
class CasNumber:
    """CAS 登记号（不可变值对象）。

    CAS 的末位是校验位（前面的数字从右往左依次乘位置号求和，模 10）。
    一个打错的 CAS 会指向别的物质甚至什么都不指向——而「管控化学品
    漏检」比「从未检查」更危险，所以任何录入的 CAS 都必须先过校验。
    """

    value: str

    # ---------------------------------------------------------------- 构造
    @classmethod
    def parse(cls, text: str) -> "CasNumber":
        """解析并校验；不合法抛 :class:`CasError`。"""
        raw = (text or "").strip()
        match = _CAS_PATTERN.match(raw)
        if not match:
            raise CasError(f"CAS 号格式非法: {text!r}（应形如 7732-18-5）")
        digits = match.group(1) + match.group(2)
        total = sum(int(d) * (i + 1) for i, d in enumerate(reversed(digits)))
        if total % 10 != int(match.group(3)):
            raise CasError(f"CAS 号校验位不符: {text!r}")
        return cls(raw)

    @classmethod
    def try_parse(cls, text: Optional[str]) -> Optional["CasNumber"]:
        """宽松解析：空或非法返回 ``None``。"""
        if not text:
            return None
        try:
            return cls.parse(str(text))
        except CasError:
            return None

    @classmethod
    def is_valid(cls, text: Optional[str]) -> bool:
        return cls.try_parse(text) is not None

    # ---------------------------------------------------------------- 属性
    @property
    def registry_id(self) -> str:
        """去掉校验位的主体部分（前两段），用于容错比对。"""
        return "-".join(self.value.split("-")[:2])

    @property
    def check_digit(self) -> int:
        return int(self.value.split("-")[2])

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:  # pragma: no cover
        return f"CasNumber({self.value!r})"


def normalize_cas_list(values: Iterable[str]) -> list[str]:
    """批量清洗 CAS 列表：去空、去重、保持原顺序。"""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = (value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


__all__ = [
    "ATOMIC_WEIGHTS",
    "FormulaError",
    "CasError",
    "MolecularFormula",
    "CasNumber",
    "combine_formulas",
    "element_counts_to_formula",
    "normalize_cas_list",
]
