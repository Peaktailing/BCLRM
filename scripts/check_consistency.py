"""一致性体检：主表的快照列与三张外设表是否还对得上。

v0.8.16 把「物质 / 批次 / 位置」从 `reagent_bottle` 拆进
`chemical_info` / `bottle_lot` / `bottle_placement`，但**没有删列**：
旧列仍在写、仍在读，新表靠一次性回填加双写长出数据。这段并存期内，两
边一旦不同步，切换读路径那天就会读出错的值——而且没人会发现，因为页
面读的是旧列，看起来完全正常。

本脚本就是那个「发现」：只读，不改任何东西。

用法::

    python scripts/check_consistency.py            # 体检，有问题退出码 1
    python scripts/check_consistency.py --limit 20 # 每类最多列 20 个例子
    python scripts/check_consistency.py --quiet    # 只出汇总

检查项：

============  ==========================================================
lot_missing   瓶没有归批（lot_id 为空）
lot_drift     瓶上的批次快照（供应商/单价/规格/单位/三个日期）与批次行不一致
place_missing 瓶没有位置记录
place_drift   位置表最新一条与瓶上的 storage_location 不一致
sub_missing   能匹配到物质档案，但瓶没关联（chemical_id 为空）
sub_drift     chemical_id 指向的档案与瓶上的 CAS / 名称都对不上
============  ==========================================================

为什么不修：修需要判断「谁对」。例如批次的单价是 12 元、瓶上是 12.5
元，是采购改了价还是入库录错了？脚本只负责把差异摆出来，让第二阶段
（双写切换）之前有人看一眼。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import Database  # noqa: E402
from config.settings import DB_MAIN_PATH  # noqa: E402

#: 瓶上是「这批货」的快照列，与 bottle_lot 的同名列一一对应
LOT_SNAPSHOT = (
    "supplier", "unit_price", "specification", "unit",
    "production_date", "inbound_date", "expiry_date",
)


def _same(left, right) -> bool:
    """快照与权威值是否等价。

    数字列用容差比较（REAL 走过一次 SQLite 往返就可能差 1e-15），
    空串与 NULL 视为同一个「没填」。
    """
    if left in (None, "") and right in (None, ""):
        return True
    try:
        return abs(float(left) - float(right)) < 1e-9
    except (TypeError, ValueError):
        return str(left or "").strip() == str(right or "").strip()


class ConsistencyReport:
    """把体检结果收成一张表：每类一个清单，键是瓶号。"""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.problems: dict[str, list[str]] = {
            "lot_missing": [],
            "lot_drift": [],
            "place_missing": [],
            "place_drift": [],
            "sub_missing": [],
            "sub_drift": [],
        }
        self.bottles = 0

    # ------------------------------------------------------------------
    def run(self) -> "ConsistencyReport":
        bottles = self.db.execute_query("SELECT * FROM reagent_bottle ORDER BY id")
        self.bottles = len(bottles)
        if not bottles:
            return self

        lots = {row["id"]: row for row in self.db.execute_query("SELECT * FROM bottle_lot")}
        places = self._current_places()
        chemicals = {row["id"]: row for row in self.db.execute_query(
            "SELECT id, name, cas_number FROM chemical_info")}
        by_cas = {(row["cas_number"] or "").strip(): row["id"]
                  for row in chemicals.values() if (row["cas_number"] or "").strip()}
        by_name = {(row["name"] or "").strip(): row["id"]
                   for row in chemicals.values() if (row["name"] or "").strip()}

        for bottle in bottles:
            number = bottle["bottle_number"]
            self._check_lot(bottle, lots, number)
            self._check_place(bottle, places, number)
            self._check_substance(bottle, chemicals, by_cas, by_name, number)
        return self

    # ------------------------------------------------------------------
    def _current_places(self) -> dict:
        """每瓶的当前位置：位置表里 id 最大的那条（与视图口径一致）。"""
        rows = self.db.execute_query(
            "SELECT bottle_number, storage_location FROM bottle_placement "
            "WHERE id IN (SELECT MAX(id) FROM bottle_placement GROUP BY bottle_number)"
        )
        return {row["bottle_number"]: row["storage_location"] for row in rows}

    def _check_lot(self, bottle, lots, number: str) -> None:
        lot_id = bottle.get("lot_id")
        if not lot_id:
            self.problems["lot_missing"].append(number)
            return
        lot = lots.get(lot_id)
        if lot is None:
            self.problems["lot_drift"].append(f"{number}（批次 #{lot_id} 已不存在）")
            return
        differing = [column for column in LOT_SNAPSHOT
                     if not _same(bottle.get(column), lot.get(column))]
        if differing:
            detail = "，".join(
                f"{column}: 瓶={bottle.get(column)!r} 批次={lot.get(column)!r}"
                for column in differing
            )
            self.problems["lot_drift"].append(f"{number}（{detail}）")

    def _check_place(self, bottle, places, number: str) -> None:
        if number not in places:
            self.problems["place_missing"].append(number)
            return
        if not _same(bottle.get("storage_location") or "", places[number] or ""):
            self.problems["place_drift"].append(
                f"{number}（瓶={bottle.get('storage_location')!r} "
                f"位置表={places[number]!r}）"
            )

    def _check_substance(self, bottle, chemicals, by_cas, by_name, number: str) -> None:
        chemical_id = bottle.get("chemical_id")
        cas = (bottle.get("cas_number") or "").strip()
        name = (bottle.get("reagent_name") or "").strip()

        if not chemical_id:
            if (cas and cas in by_cas) or (name and name in by_name):
                self.problems["sub_missing"].append(number)
            return

        substance = chemicals.get(chemical_id)
        if substance is None:
            self.problems["sub_drift"].append(f"{number}（物质 #{chemical_id} 已不存在）")
            return
        # 只要 CAS 或名称有一个对得上就算一致：瓶上的名称常带规格后缀，
        # 档案里是标准名；CAS 是强标识，名称是兜底。
        substance_cas = (substance.get("cas_number") or "").strip()
        substance_name = (substance.get("name") or "").strip()
        if (cas and substance_cas and cas == substance_cas) or (
                name and substance_name and name == substance_name):
            return
        self.problems["sub_drift"].append(
            f"{number}（瓶 CAS={cas!r} 名={name!r} → 物质 #{chemical_id} "
            f"CAS={substance_cas!r} 名={substance_name!r}）"
        )

    # ------------------------------------------------------------------
    def total(self) -> int:
        return sum(len(items) for items in self.problems.values())

    def describe(self, limit: int = 8) -> str:
        lines = [f"试剂瓶 {self.bottles} 个，问题 {self.total()} 处"]
        labels = {
            "lot_missing": "未归批",
            "lot_drift": "批次快照不一致",
            "place_missing": "无位置记录",
            "place_drift": "当前位置不一致",
            "sub_missing": "可匹配物质却未关联",
            "sub_drift": "物质关联错位",
        }
        for key, items in self.problems.items():
            if not items:
                continue
            lines.append(f"\n  {labels[key]}：{len(items)}")
            for example in items[:limit]:
                lines.append(f"    · {example}")
            if len(items) > limit:
                lines.append(f"    …其余 {len(items) - limit} 个省略")
        return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="快照列与外设表的一致性体检（只读）")
    parser.add_argument("--limit", type=int, default=8, help="每类最多列出的例子数")
    parser.add_argument("--quiet", action="store_true", help="只打印汇总行")
    parser.add_argument("--db", default=DB_MAIN_PATH, help="库路径，默认主库")
    args = parser.parse_args()

    db = Database(args.db)
    report = ConsistencyReport(db).run()
    print(report.describe(limit=1 if args.quiet else args.limit))
    return 0 if report.total() == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
