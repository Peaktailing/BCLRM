"""实验规模：一次备料的基准上下文。

「需要多少」这个问题，只有配上「做多少」才有答案。教学场景的规模是
人数与批次，科研场景可能是目标产物量或反应釜体积。把规模独立成值
对象，配方本身就不必知道自己在被谁使用——这是让教学与科研共用同一
套配方的关键。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from domain.units import Dimension, Quantity, Unit, UnitError, parse_unit


@dataclass(frozen=True)
class BatchScale:
    """一次备料规模。

    Attributes:
        persons: 参与人数（教学场景的人均口径）
        batches: 批次数（同一实验重复做的次数）
        vessel_volume: 容器/配液目标体积，供浓度型计量使用
        label: 规模说明（如「2026 秋 应用化学 2301 班」）
    """

    persons: int = 1
    batches: int = 1
    vessel_volume: Optional[Quantity] = None
    label: str = ""

    def __post_init__(self) -> None:
        if int(self.persons) < 1:
            raise ValueError("人数至少为 1")
        if int(self.batches) < 1:
            raise ValueError("批次至少为 1")
        if self.vessel_volume is not None and self.vessel_volume.unit.dimension is not Dimension.VOLUME:
            raise UnitError("容器体积必须是体积量纲")

    # ---------------------------------------------------------------- 构造
    @classmethod
    def single(cls) -> "BatchScale":
        """单人单批（科研默认 / 单次小试）。"""
        return cls()

    @classmethod
    def for_persons(cls, persons: int, batches: int = 1, label: str = "") -> "BatchScale":
        return cls(persons=int(persons), batches=int(batches), label=label)

    @classmethod
    def with_vessel(cls, volume: Any, unit: str = "mL", persons: int = 1,
                    batches: int = 1, label: str = "") -> "BatchScale":
        return cls(
            persons=int(persons),
            batches=int(batches),
            vessel_volume=Quantity.of(volume, unit),
            label=label,
        )

    # ---------------------------------------------------------------- 属性
    @property
    def multiplier(self) -> Decimal:
        """总量放大倍数 = 人数 × 批次。"""
        return Decimal(int(self.persons)) * Decimal(int(self.batches))

    @property
    def is_single(self) -> bool:
        return self.multiplier == 1

    def describe(self) -> str:
        """人话描述，直接可放报告里。"""
        parts = []
        if self.persons != 1:
            parts.append(f"{self.persons} 人")
        if self.batches != 1:
            parts.append(f"{self.batches} 批")
        if not parts:
            parts.append("单人单批")
        if self.vessel_volume is not None:
            parts.append(f"容器 {self.vessel_volume.format(2)}")
        text = " × ".join(parts)
        return f"{text}（{self.label}）" if self.label else text

    def to_record(self) -> dict:
        return {
            "persons": self.persons,
            "batches": self.batches,
            "vessel_volume": self.vessel_volume.to_float() if self.vessel_volume else None,
            "vessel_unit": self.vessel_volume.unit.symbol if self.vessel_volume else None,
            "label": self.label,
        }

    @classmethod
    def from_record(cls, record: Optional[dict]) -> "BatchScale":
        record = record or {}
        volume = record.get("vessel_volume")
        return cls(
            persons=int(record.get("persons") or 1),
            batches=int(record.get("batches") or 1),
            vessel_volume=(
                Quantity.of(volume, record.get("vessel_unit") or "mL")
                if volume not in (None, "")
                else None
            ),
            label=record.get("label") or "",
        )


def scale_of(value: Any) -> BatchScale:
    """把外部输入（None / int / dict / BatchScale）统一成 BatchScale。"""
    if isinstance(value, BatchScale):
        return value
    if value is None:
        return BatchScale.single()
    if isinstance(value, int):
        return BatchScale.for_persons(value)
    if isinstance(value, dict):
        return BatchScale.from_record(value)
    raise TypeError(f"无法识别的规模类型: {type(value).__name__}")


__all__ = ["BatchScale", "scale_of"]
