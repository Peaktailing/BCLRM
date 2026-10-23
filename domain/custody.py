"""保管权：这批试剂眼下在谁手上。

这是整个交叉点最容易被忽略、又最先决定业务形状的概念。BCLRM 的
``reagent_bottle.manager`` 存的不是「谁买的」「谁用的」，而是「谁眼下
替学校看着这批东西」——**临时所有人**。

由此推出一条硬约束：

    **教师是使用者，不是保管人。**

教师上课要用试剂，但试剂从来不记在教师名下；他用完（或没用完）都要
回到管理员手上。所以「教师申领」与「管理员申领」不是同一件事的两个
入口，而是**一条管线上前后相接的两段**：

- 第一段：教师 → 找这门课对应的管理员要（受理，保管权不变）
- 第二段：管理员 → 自己名下不够，去找别的管理员调（保管权流转）

如果这两段共用一套「把管理权转给需求人」的语义，教师就会被写成下一
任保管人，账就散了。``Custodian`` 存在的意义就是让代码里能明确区分
「谁在要」和「谁在保管」。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Iterator, Optional

from domain.substance import SubstanceRef
from domain.units import Quantity, Unit


class CustodyError(ValueError):
    """保管权相关的业务错误。"""


@dataclass(frozen=True)
class Custodian:
    """试剂保管人（管理员）。

    只承载「归属」这一个维度：姓名 + 所属科室 + 是否超管。它刻意不携带
    权限细节——权限判断在 :mod:`business.permission_service`，这里只回答
    「这批料算谁的」。
    """

    name: str
    department: str = ""
    # super_admin 是兜底保管人：无人认领的瓶挂在他名下
    is_super_admin: bool = False

    def __post_init__(self) -> None:
        if not (self.name or "").strip():
            raise CustodyError("保管人姓名不能为空")

    @property
    def key(self) -> str:
        """保管人唯一键。

        姓名在 BCLRM 里本身唯一（``person.name`` 有 UNIQUE），所以直接用
        姓名作键，不额外造编号——避免与 ``person`` 表出现两套身份。
        """
        return self.name.strip()

    @classmethod
    def of(cls, name: str, department: str = "", is_super_admin: bool = False) -> "Custodian":
        return cls(name=name, department=department, is_super_admin=is_super_admin)

    @classmethod
    def anonymous(cls) -> "Custodian":
        """未指定保管人时的占位对象（仅在展示层出现，不参与分配）。"""
        return cls(name="（未指定保管人）")

    @property
    def is_anonymous(self) -> bool:
        return self.name == "（未指定保管人）"

    def same_as(self, other: Optional["Custodian"]) -> bool:
        return other is not None and other.key == self.key

    def in_department_of(self, other: Optional["Custodian"]) -> bool:
        """是否与另一保管人同科室（第二段撮合的优先依据）。"""
        if other is None or not self.department or not other.department:
            return False
        return self.department.strip() == other.department.strip()

    def describe(self) -> str:
        if self.department:
            return f"{self.name}（{self.department}）"
        return self.name

    def __str__(self) -> str:  # pragma: no cover - 便于调试
        return self.describe()


@dataclass(frozen=True)
class Holding:
    """某一保管人名下某一物质的持有量（一个量纲一条）。"""

    custodian: Custodian
    substance: SubstanceRef
    quantity: Quantity
    lot_count: int = 1

    def describe(self) -> str:
        lots = f"／{self.lot_count} 瓶" if self.lot_count > 1 else ""
        return f"{self.substance.name or self.substance.key} {self.quantity.format(2)}{lots}"


@dataclass(frozen=True)
class Holdings:
    """保管账：按保管人切开的库存视图。

    与「全库快照」的区别只有一个，但很致命：

    - 全库快照回答「学校总共有多少」
    - 保管账回答「**这个人手上**有多少」

    教师来申领时问的必须是后者。问全库会导致受理管理员看不见自己的
    缺口，于是第二段永远不会被触发，也永远不会有人去补料。

    同类物质的不同量纲（g 与 mL）不合并——它们不能相加，硬加会算出
    无意义的数字。
    """

    holdings: tuple[Holding, ...] = ()
    # 未指定保管人的量（``is_anonymous`` 那条）
    unassigned: tuple[Holding, ...] = ()

    # ---------------------------------------------------------------- 视图
    def __iter__(self) -> Iterator[Holding]:
        return iter(self.holdings)

    def __len__(self) -> int:
        return len(self.holdings)

    def __bool__(self) -> bool:
        return bool(self.holdings)

    @property
    def custodians(self) -> tuple[Custodian, ...]:
        """账上出现过的保管人（按姓名排序，保证输出稳定）。"""
        seen: dict[str, Custodian] = {}
        for holding in self.holdings:
            seen.setdefault(holding.custodian.key, holding.custodian)
        return tuple(seen[key] for key in sorted(seen))

    def of_custodian(self, custodian: Custodian) -> tuple[Holding, ...]:
        return tuple(h for h in self.holdings if h.custodian.same_as(custodian))

    def substances(self) -> tuple[SubstanceRef, ...]:
        seen: dict[str, SubstanceRef] = {}
        for holding in self.holdings:
            seen.setdefault(holding.substance.key, holding.substance)
        return tuple(seen.values())

    # ---------------------------------------------------------------- 取量
    def of(self, custodian: Custodian, ref: SubstanceRef, unit: Unit) -> Quantity:
        """某保管人名下某物质在指定量纲上的可用量（量纲不符记零）。"""
        total = Quantity.zero(unit)
        for holding in self.holdings:
            if not holding.custodian.same_as(custodian):
                continue
            if holding.substance.key != ref.key:
                continue
            if holding.quantity.unit.dimension is not unit.dimension:
                continue
            total = total + holding.quantity.to(unit)
        return total

    def of_any_unit(self, custodian: Custodian, ref: SubstanceRef) -> tuple[Quantity, ...]:
        """某保管人名下某物质的所有量纲持有量（跨量纲换算交给中台）。"""
        found: list[Quantity] = []
        for holding in self.holdings:
            if not holding.custodian.same_as(custodian):
                continue
            if holding.substance.key != ref.key:
                continue
            found.append(holding.quantity)
        return tuple(found)

    def total_of(self, ref: SubstanceRef, unit: Unit) -> Quantity:
        """全院合计（含所有保管人）。"""
        total = Quantity.zero(unit)
        for holding in self.holdings:
            if holding.substance.key != ref.key:
                continue
            if holding.quantity.unit.dimension is not unit.dimension:
                continue
            total = total + holding.quantity.to(unit)
        return total

    # ---------------------------------------------------------------- 切分
    def others_than(self, custodian: Custodian) -> "Holdings":
        """排除某保管人后的账（第二段撮合用）。

        必须排除：受理人的量在受理那一刻就已经算过并承诺出去了，若在第二段
        再算一次，会把同一批料承诺给同一张单两次。
        """
        return Holdings(
            holdings=tuple(h for h in self.holdings if not h.custodian.same_as(custodian)),
            unassigned=self.unassigned,
        )

    def matching(self, keys: Iterable[str]) -> "Holdings":
        """只保留指定物质键的账（撮合会按缺口物质逐个收敛）。"""
        wanted = {key for key in keys}
        return Holdings(
            holdings=tuple(h for h in self.holdings if h.substance.key in wanted),
            unassigned=tuple(h for h in self.unassigned if h.substance.key in wanted),
        )

    def merge(self, other: "Holdings") -> "Holdings":
        """合并两份账（同一保管人同一物质同量纲相加）。"""
        buckets: dict[tuple[str, str, str], Holding] = {}
        for holding in list(self.holdings) + list(other.holdings):
            key = (
                holding.custodian.key,
                holding.substance.key,
                holding.quantity.unit.symbol,
            )
            existing = buckets.get(key)
            if existing is None:
                buckets[key] = holding
            else:
                buckets[key] = Holding(
                    custodian=existing.custodian,
                    substance=existing.substance,
                    quantity=existing.quantity + holding.quantity,
                    lot_count=existing.lot_count + holding.lot_count,
                )
        ordered = tuple(
            sorted(
                buckets.values(),
                key=lambda h: (h.custodian.key, h.substance.name or h.substance.key),
            )
        )
        return Holdings(holdings=ordered, unassigned=self.unassigned + other.unassigned)

    # ---------------------------------------------------------------- 摘要
    def describe(self) -> str:
        if not self.holdings:
            return "保管账为空"
        people = len(self.custodians)
        substances = len(self.substances())
        return f"{people} 名保管人 · {substances} 种物质 · {len(self.holdings)} 条持有"

    def to_rows(self) -> list[dict]:
        """展平成页面/报表用行。"""
        return [
            {
                "custodian": holding.custodian.name,
                "department": holding.custodian.department,
                "substance": holding.substance.name or holding.substance.key,
                "cas": holding.substance.cas.value if holding.substance.cas else "",
                "quantity": holding.quantity.to_float(),
                "unit": holding.quantity.unit.symbol,
                "quantity_text": holding.quantity.format(2),
                "lots": holding.lot_count,
            }
            for holding in self.holdings
        ]


def holdings_from_rows(
    rows: Iterable[dict],
    department_of=None,
) -> Holdings:
    """从「already 摊平的行」造保管账。

    每行需含 ``custodian`` / ``substance`` / ``quantity`` / ``unit``，可选
    ``cas`` / ``lots`` / ``department``。这是给数据层用的适配入口：领域
    层不认识 SQL，只认识行字典。
    """
    buckets: dict[tuple[str, str, str], Holding] = {}
    for row in rows:
        name = (row.get("custodian") or "").strip()
        if not name:
            continue
        custodian = Custodian(
            name=name,
            department=(row.get("department") or (department_of(name) if department_of else "") or ""),
        )
        substance = SubstanceRef.of(
            row.get("substance") or "", row.get("cas") or None
        )
        quantity = Quantity.of(row.get("quantity") or 0, row.get("unit") or "g")
        key = (custodian.key, substance.key, quantity.unit.symbol)
        existing = buckets.get(key)
        lots = int(row.get("lots") or 1)
        if existing is None:
            buckets[key] = Holding(custodian, substance, quantity, lots)
        else:
            buckets[key] = Holding(
                custodian, substance, existing.quantity + quantity, existing.lot_count + lots
            )
    ordered = tuple(
        sorted(
            buckets.values(),
            key=lambda h: (h.custodian.key, h.substance.name or h.substance.key),
        )
    )
    return Holdings(holdings=ordered)


def share_of(quantity: Quantity, total: Optional[Quantity]) -> Decimal:
    """占比（0~1），用于页面上的「够不够」直观表达。"""
    if total is None or total.base_value() <= 0:
        return Decimal("0")
    if quantity.unit.dimension is not total.unit.dimension:
        return Decimal("0")
    return (quantity.to(total.unit).base_value() / total.base_value()).quantize(Decimal("0.0001"))


__all__ = [
    "CustodyError",
    "Custodian",
    "Holding",
    "Holdings",
    "holdings_from_rows",
    "share_of",
]
