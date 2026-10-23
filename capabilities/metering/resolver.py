"""物质解析：把配方里的引用接到真实物性上。

配方只存引用（CAS / 分子式 / 名称），要算当量就得有分子量，要算体积
就得有密度。这些物性从哪来，是数据层的事；中台只约定一个接口：给定
引用，还我一个 :class:`domain.substance.Substance`。

用抽象基类而不是直接查库，换来两个能力：

1. 业务层可以在一次计算里复用同一份目录快照，避免一边算一边库变。
2. 测试可以塞一个内存目录，化学逻辑的验证不需要数据库。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from domain.substance import Substance, SubstanceCatalog, SubstanceRef


class SubstanceResolutionError(LookupError):
    """配方引用的物质在目录里找不到，且调用方要求必须找到。"""


class SubstanceResolver(ABC):
    """物质解析器抽象。"""

    @abstractmethod
    def resolve(self, ref: SubstanceRef) -> Optional[Substance]:
        """返回物质（找不到返回 ``None``）。"""

    def resolve_all(self, refs: Iterable[SubstanceRef]) -> dict[str, Substance]:
        """批量解析，跳过找不到的（计算时按缺物性处理）。"""
        found: dict[str, Substance] = {}
        for ref in refs:
            substance = self.resolve(ref)
            if substance is not None:
                found[ref.key] = substance
        return found

    def require(self, ref: SubstanceRef) -> Substance:
        """解析失败即报错。"""
        substance = self.resolve(ref)
        if substance is None:
            raise SubstanceResolutionError(f"物质目录中缺少 {ref}")
        return substance


class CatalogSubstanceResolver(SubstanceResolver):
    """基于内存目录的解析器（也满足 ``SubstanceCatalogLike`` 协议）。"""

    def __init__(self, catalog: Optional[SubstanceCatalog] = None) -> None:
        self._catalog = catalog or SubstanceCatalog()

    def resolve(self, ref: SubstanceRef) -> Optional[Substance]:
        return self._catalog.get(ref)

    def get(self, ref: SubstanceRef) -> Optional[Substance]:
        """兼容 :class:`domain.recipe.SubstanceCatalogLike`。"""
        return self._catalog.get(ref)

    def add(self, substance: Substance) -> None:
        self._catalog.add(substance)

    def extend(self, substances: Iterable[Substance]) -> None:
        for substance in substances:
            self._catalog.add(substance)

    def __len__(self) -> int:
        return len(self._catalog)


class ChainedSubstanceResolver(SubstanceResolver):
    """多级解析：先查本地补录，再查主数据（例如「配方专用物性」优先于
    「化学品信息表」）。"""

    def __init__(self, *resolvers: SubstanceResolver) -> None:
        self._resolvers = resolvers

    def resolve(self, ref: SubstanceRef) -> Optional[Substance]:
        for resolver in self._resolvers:
            substance = resolver.resolve(ref)
            if substance is not None:
                return substance
        return None


__all__ = [
    "SubstanceResolver",
    "SubstanceResolutionError",
    "CatalogSubstanceResolver",
    "ChainedSubstanceResolver",
]
