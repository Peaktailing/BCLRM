"""业务层端口（仓储接口）。

接口定义在**使用方**（业务层），而不是实现方（数据层）——这是依赖倒置
的实际含义：业务用例说「我需要有人帮我按 key 取出一张配方」，至于它存在
SQLite、JSON 还是别人家的 API 里，业务层不关心。

用 ``Protocol`` 而非 ``ABC``：数据层不需要显式继承，只要方法签名对得上
就能注入；测试里塞一个三十行的假仓储即可，不必构造数据库。
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, Sequence, runtime_checkable

from domain.recipe import Recipe
from domain.requirement import RequirementSheet


@runtime_checkable
class RecipeRepository(Protocol):
    """配方仓储。"""

    def get(self, key: str) -> Optional[Recipe]:
        """按业务键取配方（不存在返回 None）。"""

    def save(self, recipe: Recipe) -> Recipe:
        """按业务键 upsert（同键覆盖，版本号由调用方维护）。"""

    def delete(self, key: str) -> bool:
        """物理删除（一般用归档代替）。"""

    def list(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        source_kind: Optional[str] = None,
        limit: int = 200,
    ) -> list[Recipe]:
        """列表查询。"""

    def exists(self, key: str) -> bool:
        ...


@runtime_checkable
class RequirementRepository(Protocol):
    """需求单仓储（只追加，不回改历史）。"""

    def save(
        self,
        sheet: RequirementSheet,
        requester: str,
        snapshot_data: Optional[dict[str, Any]] = None,
    ) -> str:
        """保存需求单，返回单据号。"""

    def get(self, sheet_number: str) -> Optional[RequirementSheet]:
        ...

    def list_recent(self, limit: int = 50) -> list[dict]:
        ...


@runtime_checkable
class StockProvider(Protocol):
    """库存快照来源。

    返回 ``capabilities.supply.StockSnapshot``。业务层不直接读库存表，
    而是通过这个端口拿一份快照——计算与查询彻底解耦。
    """

    def snapshot(self, label: str = "") -> Any:
        ...


__all__ = ["RecipeRepository", "RequirementRepository", "StockProvider"]
