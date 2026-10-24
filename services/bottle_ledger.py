"""入库之后的三件外设：物质指针、来源批次、位置轨迹。

`reagent_bottle` 只该回答「这一瓶」。另外三件事各有各的家，判据是
「谁共享这一行」：

===============  ==============================  ==========================
这件事           谁共享                          落在哪
===============  ==============================  ==========================
物质是什么       所有含这种物质的瓶              chemical_info（CAS 唯一）
这批货从哪来     同一次到货的若干瓶              bottle_lot
现在/曾经在哪    只有这一瓶，但每次挪动都要留痕  bottle_placement
===============  ==============================  ==========================

v0.8.16 把主表里属于这三类的列原地留成了**快照**（表定义里带 ☆），并用
回填把新表建起来。本模块负责此后每一天的**双写**：新瓶入库时同时落
批次与位置，挪动时追加一条位置。旧列仍在写、仍在读——第二阶段切读
路径之前，它们仍是真理源；但新表必须与它们同步长，否则切换那天要靠
一次性的大迁移补历史，而历史已经补不全了。

为什么归批靠签名而不是靠批号：瓶上没有厂家批号可依据（采购单里才有，
而且经常没填）。能拿到的最强签名是「同一物质 + 同一供应商 + 同一单价
+ 同一规格」——同一次到货的这几瓶，这四项必然相同；不同次到货若四项
全同，归成一批也不影响任何判断（有效期、单价、供应商都一样）。
由此带来的边界：**同一次到货里有一瓶改了单价**，它会被归成另一批。
这是可接受的误差，比「每瓶一批」更接近事实。

本模块不做判断，只做落表：物质能不能定位是 `chemical_service` 的事，
批次的业务含义由读路径决定。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from db.base_service import BaseService
from services.base.chemical_service import chemical_service
from services.core.reagent_bottle_service import reagent_bottle_service
from utils.error_handler import logger

# 一次到货的签名。四项全同即归同一批（见模块说明）。
LOT_SIGNATURE = ("chemical_id", "supplier", "unit_price", "specification")

# 瓶上属于「这批货」的列：双写时从瓶搬到批次，键是批次列，值是瓶列。
LOT_FROM_BOTTLE = {
    "supplier": "supplier",
    "unit_price": "unit_price",
    "specification": "specification",
    "unit": "unit",
    "production_date": "production_date",
    "inbound_date": "inbound_date",
    "expiry_date": "expiry_date",
}


class _LotService(BaseService):
    """bottle_lot 的单表读写。

    不继承 `ReagentBottleService`：批次与瓶是两个东西，混在一起早晚会
    有人拿批次的 id 去当瓶号。表里没有 `rev` 列，写入不推进版本
    （版本只服务「这一行被并发改过」的场景，批次是入库时一次写定的）。
    """

    def __init__(self, db=None) -> None:
        super().__init__("bottle_lot", db=db)


class _PlacementService(BaseService):
    """bottle_placement 的单表读写：一次挪动一条，只追加不修改。"""

    def __init__(self, db=None) -> None:
        super().__init__("bottle_placement", db=db)


class BottleLedger:
    """把一瓶的入库事实落到三张外设表上。"""

    def __init__(
        self,
        bottles=None,
        lots: Optional[_LotService] = None,
        placements: Optional[_PlacementService] = None,
        chemicals=None,
        db=None,
    ) -> None:
        self.bottles = bottles or reagent_bottle_service
        self.db = db or self.bottles.db
        self.lots = lots or _LotService(db=self.db)
        self.placements = placements or _PlacementService(db=self.db)
        self.chemicals = chemicals or chemical_service

    # ------------------------------------------------------------------
    # 物质
    # ------------------------------------------------------------------
    def chemical_for(self, cas_number: Optional[str], name: Optional[str]) -> Optional[int]:
        """这瓶装的是什么，返回 chemical_info.id。

        CAS 优先、名称兜底，与回填的口径一致。两条都查不到返回 None——
        **不自动建档**：瓶上写的名字可能是错的、可能是混合物、也可能是
        供应商的商标，替它建一条档案等于把错误固化进主数据。
        """
        cas = (cas_number or "").strip()
        if cas:
            found = self.chemicals.get_by_cas_number(cas)
            if found is not None:
                return getattr(found, "id", None)
        label = (name or "").strip()
        if label:
            found = self.chemicals.get_by_name(label)
            if found is not None:
                return getattr(found, "id", None)
        return None

    # ------------------------------------------------------------------
    # 批次
    # ------------------------------------------------------------------
    def lot_for(self, chemical_id: Optional[int], fields: Dict[str, Any]) -> Optional[int]:
        """按签名找批次，找不到就建一条，返回批次 id。

        `fields` 是入库时写给瓶的那份数据，键用瓶的列名。
        """
        signature = {
            "chemical_id": chemical_id,
            "supplier": fields.get("supplier"),
            "unit_price": fields.get("unit_price"),
            "specification": fields.get("specification"),
        }
        found = self._existing_lot(signature)
        if found is not None:
            return found

        row = dict(signature)
        for lot_column, bottle_column in LOT_FROM_BOTTLE.items():
            row[lot_column] = fields.get(bottle_column)
        row.setdefault("unit", "g")
        row["notes"] = ""
        try:
            lot_id = self.lots.create(row)
            logger.info("新建来源批次", chemical_id=chemical_id, lot_id=lot_id)
            return lot_id
        except Exception as exc:
            logger.error(f"新建来源批次失败: {exc}", exception=exc)
            raise

    def _existing_lot(self, signature: Dict[str, Any]) -> Optional[int]:
        """签名四项全同即同一批。

        用 `IS` 而不是 `=`：`=` 遇 NULL 恒不成立，会把「供应商没填」的
        瓶子每次都建成新批。SQLite 的 `IS` 是空值安全的相等。
        """
        where = " AND ".join(f"{column} IS ?" for column in LOT_SIGNATURE)
        rows = self.lots.db.execute_query(
            f"SELECT id FROM bottle_lot WHERE {where} ORDER BY id LIMIT 1",
            tuple(signature.get(column) for column in LOT_SIGNATURE),
        )
        return rows[0]["id"] if rows else None

    # ------------------------------------------------------------------
    # 指针与位置
    # ------------------------------------------------------------------
    def attach(
        self,
        bottle_number: str,
        fields: Dict[str, Any],
        *,
        moved_by: str = "",
        note: str = "入库",
    ) -> Dict[str, Optional[int]]:
        """一瓶入库完成后调用：定位物质、归入批次、落下第一条位置。

        `fields` 用入库时写给瓶的那份数据（瓶列名），这样「写瓶」与
        「写外设」永远取自同一个来源，不会各算各的。
        """
        chemical_id = self.chemical_for(fields.get("cas_number"), fields.get("reagent_name"))
        lot_id = self.lot_for(chemical_id, fields)
        self._point_to(bottle_number, chemical_id, lot_id)
        self.move_to(
            bottle_number,
            fields.get("storage_location") or "",
            moved_by=moved_by,
            note=note,
        )
        if chemical_id is None:
            logger.warning(
                "入库未关联物质档案（CAS 与名称都没有命中，不自动建档）",
                bottle_number=bottle_number,
                cas_number=fields.get("cas_number"),
                reagent_name=fields.get("reagent_name"),
            )
        return {"chemical_id": chemical_id, "lot_id": lot_id}

    def _point_to(self, bottle_number: str, chemical_id: Optional[int],
                  lot_id: Optional[int]) -> None:
        """把物质与批次指针写回瓶。解析不到的不写，留 NULL 等档案补齐。"""
        pointers = {}
        if chemical_id is not None:
            pointers["chemical_id"] = chemical_id
        if lot_id is not None:
            pointers["lot_id"] = lot_id
        if pointers:
            self.bottles.update_by_field("bottle_number", bottle_number, pointers)

    def move_to(
        self,
        bottle_number: str,
        location: str,
        *,
        moved_by: str = "",
        note: str = "",
    ) -> Optional[int]:
        """挪一瓶：追加一条位置历史，并把当前位置写回主表。

        「当前位置」在主表上是一个**为读路径服务的缓存**，权威答案是
        位置表里 id 最大的那条（见视图 `v_bottle_current_place`）。两者
        在同一次调用里一起写，避免出现「瓶说在 A、位置表说在 B」。
        """
        moved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        placement_id = self.placements.create({
            "bottle_number": bottle_number,
            "storage_location": location,
            "moved_at": moved_at,
            "moved_by": moved_by or "",
            "note": note or "",
        })
        self.bottles.update_by_field(
            "bottle_number",
            bottle_number,
            {"storage_location": location, "placement_at": moved_at},
        )
        return placement_id

    # ------------------------------------------------------------------
    # 当前值（读路径暂用主表缓存，切换后改用这里）
    # ------------------------------------------------------------------
    def current_place(self, bottle_number: str) -> Optional[str]:
        """这一瓶现在的存放位置：位置表里 id 最大的那条。"""
        rows = self.placements.db.execute_query(
            "SELECT storage_location FROM bottle_placement "
            "WHERE bottle_number = ? ORDER BY id DESC LIMIT 1",
            (bottle_number,),
        )
        return rows[0]["storage_location"] if rows else None


bottle_ledger = BottleLedger()

__all__ = ["BottleLedger", "bottle_ledger", "LOT_SIGNATURE", "LOT_FROM_BOTTLE"]
