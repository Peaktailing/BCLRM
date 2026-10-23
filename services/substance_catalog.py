"""物质目录装配：把 ``chemical_info`` 读成中台可用的物性目录。

BCLRM 的化学品信息表已经有 ``formula`` 与 ``cas_number``——这两列足够
让「分子量」从式子算出来，不需要额外维护一列。密度目前缺失，缺失时
体积↔质量的换算会明确报错，而不会瞎猜一个 1.0。

这里刻意做成「一次加载全表 + 内存索引」：化学品信息通常几百到几千条，
一次加载后同一次计算里反复命中，比逐条查库快一个数量级，也避免了
「边算边库变」。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, Mapping, Optional

from capabilities.metering.resolver import CatalogSubstanceResolver
from domain.substance import Substance
from utils.error_handler import logger

#: 纯度文本里能识别的百分比写法，如 "99.5%" / "≥99%"
_PERCENT_HINTS = ("%",)


def parse_purity(text: Optional[str]) -> Optional[Decimal]:
    """从纯度文本里抽百分比：``"99.5%"`` → 0.995；``"AR"`` → None。

    只认明确的百分比。等级词（AR/CP/GR）不对应唯一含量，不猜。
    """
    raw = (text or "").strip()
    if not raw or not any(hint in raw for hint in _PERCENT_HINTS):
        return None
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    try:
        value = Decimal(digits)
    except Exception:
        return None
    if value <= 0:
        return None
    if value > 1:
        value = value / Decimal("100")
    return value if value <= 1 else None


def substance_from_chemical_row(row: Mapping[str, Any]) -> Optional[Substance]:
    """一行 ``chemical_info`` → :class:`Substance`。

    ``display_name`` 优先作为显示名（同一物质在库里可能有俗名）。
    """
    name = (row.get("display_name") or row.get("name") or "").strip()
    cas = (row.get("cas_number") or "").strip() or None
    formula = (row.get("formula") or "").strip() or None
    if not (name or cas or formula):
        return None

    default_unit = "mL" if row.get("reagent_type") and "液" in str(row.get("reagent_type")) else "g"
    try:
        return Substance.of(
            name=name,
            cas=cas,
            formula=formula,
            purity=float(parse_purity(row.get("purity")) or 0) or None,
            controlled=bool(row.get("controlled_type")),
            default_unit=default_unit,
        )
    except Exception as exc:
        logger.error(f"化学品行解析失败 name={name!r}: {exc}", exception=exc)
        return None


class ChemicalInfoResolver(CatalogSubstanceResolver):
    """基于 ``chemical_info`` 一次性装载的物性目录。"""

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, Any]]) -> "ChemicalInfoResolver":
        resolver = cls()
        loaded = 0
        for row in rows:
            substance = substance_from_chemical_row(row)
            if substance is not None:
                resolver.add(substance)
                loaded += 1
        logger.info(f"物质目录装载完成：{loaded} 条")
        return resolver

    @classmethod
    def from_database(cls, chemical_service=None) -> "ChemicalInfoResolver":
        """从数据库装载（延迟导入，避免测试环境在装配阶段就摸库）。"""
        if chemical_service is None:
            from services.base.chemical_service import chemical_service as _svc
            chemical_service = _svc
        try:
            rows = chemical_service.get_all(order_by="name")
        except Exception as exc:
            logger.error(f"化学品信息读取失败，物质目录为空: {exc}", exception=exc)
            rows = []
        return cls.from_rows(rows)


def build_resolver(rows: Optional[Iterable[Mapping[str, Any]]] = None) -> ChemicalInfoResolver:
    """便捷入口：给行就用行，不给就查库。"""
    if rows is not None:
        return ChemicalInfoResolver.from_rows(rows)
    return ChemicalInfoResolver.from_database()


__all__ = [
    "parse_purity",
    "substance_from_chemical_row",
    "ChemicalInfoResolver",
    "build_resolver",
]
