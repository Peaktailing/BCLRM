"""从活库装配保管账。

一件事：把 ``reagent_bottle`` 的当前状态，连同 ``person.department``，
装成中台能用的 :class:`~capabilities.circulation.ledger.SnapshotLedger`。

为什么要有这一层而不是让业务层直接查表：领域与中台都不认识 SQL，
而「批量读瓶 + 拼科室」这种装配活既枯燥又容易写错（比如把已报废的瓶
算进可用量）。放在这里统一写一次，全站只有一个口径。
"""
from __future__ import annotations

from typing import Optional

from capabilities.circulation.ledger import SnapshotLedger
from capabilities.supply.availability import AvailabilityPolicy
from capabilities.supply.stock import StockSnapshot
from db.database import db


class CustodyLedgerAssembler:
    """把活库装成保管账。"""

    def __init__(self, database=None, policy: Optional[AvailabilityPolicy] = None) -> None:
        self.db = database or db
        self.policy = policy
        self._departments: Optional[dict[str, str]] = None

    # ---------------------------------------------------------------- 部门
    def departments(self, refresh: bool = False) -> dict[str, str]:
        """``person.name → department``。

        科室会随人事变动，所以默认每次重建；需要批量渲染页面时可以传
        ``refresh=False`` 复用同一份快照。
        """
        if self._departments is not None and not refresh:
            return self._departments
        rows = self.db.execute_query("SELECT name, department FROM person")
        self._departments = {
            (row.get("name") or "").strip(): (row.get("department") or "").strip()
            for row in rows
            if (row.get("name") or "").strip()
        }
        return self._departments

    def department_of(self, name: str) -> str:
        return self.departments().get((name or "").strip(), "")

    # ---------------------------------------------------------------- 装配
    def bottle_rows(self) -> list[dict]:
        """全部试剂瓶（含不可用的：可用性由策略过滤，不由 SQL 过滤）。

        刻意不在 SQL 里加 ``WHERE``：口径分两处维护迟早会漂移。让
        ``AvailabilityPolicy`` 做唯一裁判。
        """
        return self.db.execute_query("SELECT * FROM reagent_bottle")

    def build(self) -> SnapshotLedger:
        """当前时刻的保管账。"""
        snapshot = StockSnapshot.from_bottle_rows(
            self.bottle_rows(), label="活库快照"
        )
        return SnapshotLedger(
            snapshot,
            policy=self.policy,
            department_of=self.department_of,
        )

    # ---------------------------------------------------------------- 摘要
    def summary(self) -> dict:
        """页面顶部的一行摘要。"""
        ledger = self.build()
        unclaimed = ledger.unclaimed()
        return {
            "custodians": len(ledger.custodians()),
            "lots": len(ledger.snapshot()),
            "unclaimed_lots": len(unclaimed),
            "unclaimed_names": sorted(
                {lot.substance.name or lot.substance.key for lot in unclaimed}
            ),
            "text": ledger.describe(),
        }


custody_ledger_assembler = CustodyLedgerAssembler()


__all__ = ["CustodyLedgerAssembler", "custody_ledger_assembler"]
