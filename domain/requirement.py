"""需求单：配方 × 规模 算出来的那张备料清单。

它是交叉点上真正流通的凭证——向上承接配方，向下驱动采购与流转。
设计上刻意把它做成**不可变快照**：算出来的那一刻就冻结，后面库存
怎么变都不回写它。要重算就产生新的一张，历史因此可追溯（谁在什么
库存状态下批的这批料，事后查得到）。

缺口评估（:meth:`RequirementSheet.coverage_with`）接收一份「物质 →
可用量」的映射，而不去问库存服务——领域层不认识库存，只认识数字。
可用量怎么算（扣过期、扣管控、扣预占）是中台 supply 的职责。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Iterator, Mapping, Optional

from domain.batch import BatchScale
from domain.recipe import SourceRef
from domain.substance import ComponentRole, SubstanceRef
from domain.units import Dimension, Quantity, Unit, parse_unit


@dataclass(frozen=True)
class RequirementLine:
    """需求清单的一行。"""

    substance: SubstanceRef
    role: ComponentRole
    quantity: Quantity
    basis_text: str = ""
    explanation: str = ""
    purity_required: Optional[Decimal] = None
    controlled: bool = False
    seq: int = 0

    def __post_init__(self) -> None:
        if self.quantity.is_negative():
            raise ValueError(f"{self.substance} 的需求量不能为负")

    @property
    def key(self) -> str:
        return self.substance.key

    @property
    def name(self) -> str:
        return self.substance.name or str(self.substance)

    def with_quantity(self, quantity: Quantity) -> "RequirementLine":
        return RequirementLine(
            substance=self.substance,
            role=self.role,
            quantity=quantity,
            basis_text=self.basis_text,
            explanation=self.explanation,
            purity_required=self.purity_required,
            controlled=self.controlled,
            seq=self.seq,
        )

    def to_record(self, sheet_id: Optional[int] = None) -> dict:
        record = {
            "seq": self.seq,
            "substance_key": self.substance.key,
            "display_name": self.substance.name,
            "cas_number": self.substance.cas.value if self.substance.cas else None,
            "role": self.role.value,
            "quantity": self.quantity.to_float(),
            "unit": self.quantity.unit.symbol,
            "basis_text": self.basis_text,
            "explanation": self.explanation,
            "purity_required": (
                float(self.purity_required) if self.purity_required is not None else None
            ),
            "is_controlled": 1 if self.controlled else 0,
        }
        if sheet_id is not None:
            record["sheet_id"] = sheet_id
        return record

    @classmethod
    def from_record(cls, record: dict) -> "RequirementLine":
        return cls(
            substance=SubstanceRef.of(
                record.get("display_name") or "",
                record.get("cas_number"),
                record.get("formula"),
            ),
            role=ComponentRole(record.get("role") or ComponentRole.REAGENT.value),
            quantity=Quantity.of(
                record.get("quantity") or 0, record.get("unit") or "g"
            ),
            basis_text=record.get("basis_text") or "",
            explanation=record.get("explanation") or "",
            purity_required=(
                Decimal(str(record["purity_required"]))
                if record.get("purity_required") not in (None, "")
                else None
            ),
            controlled=bool(record.get("is_controlled")),
            seq=int(record.get("seq") or 0),
        )


@dataclass(frozen=True)
class CoverageLine:
    """需求 vs 可用量的对账结果。"""

    requirement: RequirementLine
    available: Quantity

    @property
    def required(self) -> Quantity:
        return self.requirement.quantity

    @property
    def gap(self) -> Quantity:
        """缺口（不足时为正，足够时为零）。"""
        missing = self.required - self.available
        return missing.clamp_non_negative()

    @property
    def is_covered(self) -> bool:
        return self.gap.is_zero()

    @property
    def coverage_ratio(self) -> Decimal:
        """覆盖率 0~1（需求为零时视为完全覆盖）。"""
        required = self.required.base_value()
        if required <= 0:
            return Decimal("1")
        covered = min(self.available.base_value(), required)
        return (covered / required).quantize(Decimal("0.0001"))

    def describe(self) -> str:
        if self.is_covered:
            return f"{self.requirement.name} 需 {self.required.format(2)}，可用 {self.available.format(2)}"
        return (
            f"{self.requirement.name} 需 {self.required.format(2)}，"
            f"可用 {self.available.format(2)}，缺 {self.gap.format(2)}"
        )


@dataclass(frozen=True)
class CoverageReport:
    """整张需求单的供应可达性。"""

    lines: tuple[CoverageLine, ...] = ()

    @property
    def shortages(self) -> tuple[CoverageLine, ...]:
        return tuple(line for line in self.lines if not line.is_covered)

    @property
    def covered(self) -> tuple[CoverageLine, ...]:
        return tuple(line for line in self.lines if line.is_covered)

    @property
    def is_fully_covered(self) -> bool:
        return not self.shortages

    @property
    def ratio(self) -> Decimal:
        """行级覆盖率：完全满足的行 / 总行数。"""
        if not self.lines:
            return Decimal("1")
        return (Decimal(len(self.covered)) / Decimal(len(self.lines))).quantize(
            Decimal("0.0001")
        )

    def summary(self) -> str:
        if not self.lines:
            return "无需求行"
        if self.is_fully_covered:
            return f"{len(self.lines)} 项全部可从现有库存满足"
        return (
            f"{len(self.covered)}/{len(self.lines)} 项可满足，"
            f"{len(self.shortages)} 项需补货"
        )


@dataclass(frozen=True)
class RequirementSheet:
    """需求单（不可变快照）。"""

    recipe_key: str
    title: str
    scale: BatchScale
    lines: tuple[RequirementLine, ...] = ()
    computed_at: datetime = field(default_factory=datetime.now)
    source: Optional[SourceRef] = None
    warnings: tuple[str, ...] = ()

    # ---------------------------------------------------------------- 视图
    def __iter__(self) -> Iterator[RequirementLine]:
        return iter(self.lines)

    def __len__(self) -> int:
        return len(self.lines)

    @property
    def controlled_lines(self) -> tuple[RequirementLine, ...]:
        return tuple(line for line in self.lines if line.controlled)

    def line_of(self, ref: SubstanceRef) -> Optional[RequirementLine]:
        for line in self.lines:
            if line.key == ref.key:
                return line
        return None

    def of_role(self, role: ComponentRole) -> tuple[RequirementLine, ...]:
        return tuple(line for line in self.lines if line.role is role)

    def totals_by_dimension(self) -> dict[str, int]:
        """按量纲统计行数（需求单摘要用）。"""
        counts: dict[str, int] = {}
        for line in self.lines:
            counts[line.quantity.unit.dimension.label] = (
                counts.get(line.quantity.unit.dimension.label, 0) + 1
            )
        return counts

    def total_in(self, unit: Unit) -> Quantity:
        """某量纲下的合计（其他量纲的行自动跳过）。"""
        target = unit if isinstance(unit, Unit) else parse_unit(unit)
        total = Quantity.zero(target)
        for line in self.lines:
            if line.quantity.unit.dimension is target.dimension:
                total = total + line.quantity.to(target)
        return total

    def explain(self) -> list[str]:
        """逐行推导，报告/审计用。"""
        return [
            f"{line.seq + 1}. {line.name}：{line.explanation or line.basis_text or line.quantity.format(3)}"
            for line in self.lines
        ]

    # ---------------------------------------------------------------- 对账
    def coverage_with(self, available_by_key: Mapping[str, Quantity]) -> CoverageReport:
        """与可用量对账。

        Args:
            available_by_key: 物质引用键 → 可用量。缺键视为零库存。
        """
        lines: list[CoverageLine] = []
        for line in self.lines:
            available = available_by_key.get(line.key)
            if available is None:
                available = Quantity.zero(line.quantity.unit)
            elif available.unit.dimension is not line.quantity.unit.dimension:
                # 量纲对不上（库存按体积、需求按质量）：不做魔法换算，
                # 计为零可用，交给上层用物质密度处理后再传进来。
                available = Quantity.zero(line.quantity.unit)
            else:
                available = available.to(line.quantity.unit)
            lines.append(CoverageLine(line, available))
        return CoverageReport(tuple(lines))

    # ---------------------------------------------------------------- 序列化
    def to_record(self) -> dict:
        return {
            "recipe_key": self.recipe_key,
            "title": self.title,
            "computed_at": self.computed_at.isoformat(timespec="seconds"),
            "source_kind": self.source.kind.value if self.source else None,
            "source_code": self.source.code if self.source else None,
            "warnings": list(self.warnings),
            **{f"scale_{k}": v for k, v in self.scale.to_record().items()},
        }

    def describe(self) -> str:
        return (
            f"{self.title}（{self.scale.describe()}）：{len(self.lines)} 项备料"
            + (f"，其中 {len(self.controlled_lines)} 项受管控" if self.controlled_lines else "")
        )


def merge_sheets(sheets: Iterable[RequirementSheet], title: str = "合并需求") -> RequirementSheet:
    """合并多张需求单（同一批领用里多个实验一起备料时用）。

    同一物质多行合并为一行；量纲不同则保留多行（质量与体积不能直接相加）。
    """
    sheets = list(sheets)
    if not sheets:
        raise ValueError("没有可合并的需求单")

    buckets: dict[tuple[str, str], RequirementLine] = {}
    warnings: list[str] = []
    for sheet in sheets:
        warnings.extend(sheet.warnings)
        for line in sheet.lines:
            key = (line.key, line.quantity.unit.dimension.value)
            existing = buckets.get(key)
            if existing is None:
                buckets[key] = line
            else:
                buckets[key] = existing.with_quantity(existing.quantity + line.quantity)

    merged_lines = tuple(
        sorted(buckets.values(), key=lambda line: (line.seq, line.name))
    )
    return RequirementSheet(
        recipe_key="+".join(sheet.recipe_key for sheet in sheets),
        title=title,
        scale=sheets[0].scale,
        lines=merged_lines,
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = [
    "RequirementLine",
    "CoverageLine",
    "CoverageReport",
    "RequirementSheet",
    "merge_sheets",
]
