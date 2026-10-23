"""库存快照：把「一瓶一瓶的实物」读成供应侧能算的形状。

BCLRM 的库存主表是 ``reagent_bottle``，状态用中文字符串表达（可借 /
已借出 / 耗尽 / 空瓶，正常 / 即将过期 / 已过期）。中台不吞这些字符串，
而是由 :meth:`StockLot.from_bottle_row` 这一处适配器翻译成枚举与布尔，
再往上就只剩「能不能用」的判断，业务代码不必再认中文状态词。

这样做的直接好处：将来换数据库、换状态词、接科研仓库，只需要改这一
个适配方法，供应策略与计算逻辑一行不动。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from domain.substance import SubstanceRef
from domain.units import Dimension, Quantity, Unit, parse_unit


class ExpiryState(str, Enum):
    """效期状态（与 BCLRM ``expired_flag`` 一一对应）。"""

    FRESH = "正常"
    EXPIRING = "即将过期"
    EXPIRED = "已过期"
    UNKNOWN = "待确认"

    @property
    def is_usable(self) -> bool:
        """过期不可用；待确认按可用处理（数据缺失不该让库存凭空消失，
        由策略层决定是否更保守）。"""
        return self is not ExpiryState.EXPIRED

    @classmethod
    def parse(cls, text: Optional[str]) -> "ExpiryState":
        for state in cls:
            if state.value == (text or "").strip():
                return state
        return cls.UNKNOWN


_BORROWABLE_WORDS = {"可借"}
_SCRAP_WORDS = {"待报废", "已报废"}


def _dec(value: Any, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _parse_date(text: Optional[str]) -> Optional[date]:
    raw = (text or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw[: len(fmt) + 2], fmt).date()
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(raw).date()
    except (ValueError, TypeError):
        return None


# 出库紧迫度：数字小的先出（EXPIRED 正常进不来，给了 0 以防策略放宽）
_EXPIRY_URGENCY = {
    ExpiryState.EXPIRED: 0,
    ExpiryState.EXPIRING: 1,
    ExpiryState.FRESH: 2,
}


@dataclass(frozen=True)
class StockLot:
    """一个可计量的库存批次（通常就是一瓶试剂）。"""

    lot_id: str
    substance: SubstanceRef
    quantity: Quantity
    expiry: ExpiryState = ExpiryState.FRESH
    borrowable: bool = True
    scrapped: bool = False
    controlled: bool = False
    location: str = ""
    specification: Optional[Quantity] = None
    expires_on: Optional[date] = None
    unit_price: Optional[Decimal] = None
    # 保管人：这批试剂在谁名下。BCLRM 的 reagent_bottle.manager 即此意。
    # 空串表示尚未指定保管人（归超级管理员统一兜底）。它不是"使用者"，
    # 而是"临时所有人"——教师使用试剂但不持有保管权。
    custodian: str = ""
    # 开封日期：非空即已开封。抽卡时已开封的先出（少开一瓶是一瓶），
    # 来源是 reagent_bottle.unseal_date。它同时是效期风险的信号——开封后
    # 的保质期比未开封短，先消耗它两头都对。
    opened_on: Optional[date] = None

    # ---------------------------------------------------------------- 判定
    @property
    def is_empty(self) -> bool:
        return self.quantity.base_value() <= 0

    @property
    def is_expired(self) -> bool:
        return self.expiry is ExpiryState.EXPIRED

    @property
    def days_to_expiry(self) -> Optional[int]:
        if self.expires_on is None:
            return None
        return (self.expires_on - date.today()).days

    @property
    def urgency(self) -> int:
        """效期紧急度的数值化（越小越急）。

        抽卡排序单独用这一位，比 ``fefo_key`` 的元组更适合拼进更长的键。
        """
        return _EXPIRY_URGENCY.get(self.expiry, 5)

    @property
    def fefo_key(self) -> tuple:
        """先到期先用（First Expired First Out）的排序键。

        状态比日期更紧急：标了临期的瓶即使没填日期，也该先出。同状态内
        再按到期日、批次号排，保证顺序稳定可复现。
        """
        return (self.urgency, self.expires_on or date.max, self.lot_id)

    def describe(self) -> str:
        bits = [self.lot_id, self.quantity.format(2)]
        if self.expiry is not ExpiryState.FRESH:
            bits.append(self.expiry.value)
        if self.location:
            bits.append(self.location)
        return " · ".join(bits)

    # ---------------------------------------------------------------- 适配
    @classmethod
    def from_bottle_row(cls, row: Mapping[str, Any]) -> "StockLot":
        """从 ``reagent_bottle`` 的一行构造批次。

        这是**唯一**知道 BCLRM 字段名与中文状态词的地方。
        """
        unit = parse_unit(row.get("unit"), default=parse_unit("g"))
        specification_value = row.get("specification")
        return cls(
            lot_id=str(row.get("bottle_number") or row.get("id") or ""),
            substance=SubstanceRef.of(
                row.get("reagent_name") or "", row.get("cas_number")
            ),
            quantity=Quantity(_dec(row.get("remaining_quantity")), unit),
            expiry=ExpiryState.parse(row.get("expired_flag")),
            borrowable=(row.get("borrowable_flag") or "").strip() in _BORROWABLE_WORDS
            and bool(row.get("borrowable_check", 1)),
            scrapped=(row.get("scrap_flag") or "").strip() in _SCRAP_WORDS,
            controlled=bool(row.get("is_controlled")),
            location=row.get("storage_location") or "",
            specification=(
                Quantity(_dec(specification_value), unit)
                if specification_value not in (None, "")
                else None
            ),
            expires_on=_parse_date(row.get("expiry_date")),
            unit_price=(
                _dec(row.get("unit_price")) if row.get("unit_price") not in (None, "") else None
            ),
            custodian=(row.get("manager") or "").strip(),
            opened_on=_parse_date(row.get("unseal_date")),
        )


@dataclass(frozen=True)
class StockSnapshot:
    """某一时刻的库存快照（只读）。

    计算必须基于快照而不是活库：一张需求单从算到批的过程中库存会变，
    快照让「当时按什么算的」可复盘。
    """

    lots: tuple[StockLot, ...] = ()
    taken_at: datetime = field(default_factory=datetime.now)
    label: str = ""

    # ---------------------------------------------------------------- 构造
    @classmethod
    def of(cls, lots: Iterable[StockLot], label: str = "") -> "StockSnapshot":
        return cls(tuple(lots), datetime.now(), label)

    @classmethod
    def from_bottle_rows(cls, rows: Iterable[Mapping[str, Any]], label: str = "") -> "StockSnapshot":
        return cls.of((StockLot.from_bottle_row(row) for row in rows), label)

    # ---------------------------------------------------------------- 查询
    def __len__(self) -> int:
        return len(self.lots)

    def __iter__(self):
        return iter(self.lots)

    def pool(self, ref: SubstanceRef) -> tuple[StockLot, ...]:
        """某物质的全部批次（含不可用的，由策略过滤）。"""
        return tuple(lot for lot in self.lots if lot.substance.matches(ref))

    def on_hand(self, ref: SubstanceRef, unit: Unit) -> Quantity:
        """某物质的在库合计（不过滤可用性），同量纲换算到 ``unit``。"""
        target = unit if isinstance(unit, Unit) else parse_unit(unit)
        total = Quantity.zero(target)
        for lot in self.pool(ref):
            if lot.quantity.unit.dimension is target.dimension:
                total = total + lot.quantity.to(target)
        return total

    def dimensions_of(self, ref: SubstanceRef) -> set[Dimension]:
        return {lot.quantity.unit.dimension for lot in self.pool(ref)}

    def substance_keys(self) -> set[str]:
        return {lot.substance.key for lot in self.lots}

    def describe(self) -> str:
        if not self.lots:
            return "库存快照：空"
        return (
            f"库存快照：{len(self.lots)} 个批次 / {len(self.substance_keys())} 种物质"
            f"（{self.taken_at.strftime('%Y-%m-%d %H:%M')}）"
            + (f" · {self.label}" if self.label else "")
        )


__all__ = ["ExpiryState", "StockLot", "StockSnapshot"]
