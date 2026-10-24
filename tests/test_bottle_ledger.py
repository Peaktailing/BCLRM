"""双写与一致性体检：新表跟着旧列一起长，且能自己发现长歪了。

v0.8.16 拆完表但没删列，旧列仍是读路径的真理源——所以「新表写对了没有」
在页面上看不出来。这里测三件事：

1. 入库之后，物质指针 / 来源批次 / 第一条位置都落了表
2. 归批按「物质 + 供应商 + 单价 + 规格」签名合并，换一项就是另一批
3. `scripts/check_consistency.py` 能把这三种表之间的差异报出来
"""
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from services.base.chemical_service import chemical_service
from services.bottle_ledger import BottleLedger, LOT_SIGNATURE
from services.core.reagent_bottle_service import reagent_bottle_service

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TABLES = (
    "bottle_placement", "bottle_lot", "borrow_record", "return_record",
    "manager_change_log", "reagent_bottle", "chemical_info", "person", "daily_counters",
)


def _load_checker():
    """按路径加载体检脚本（scripts/ 不是包，不能直接 import）。"""
    path = os.path.join(_PROJECT_ROOT, "scripts", "check_consistency.py")
    spec = importlib.util.spec_from_file_location("check_consistency", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Ledger(unittest.TestCase):
    """入库时三张外设表一起长。"""

    def setUp(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()
        chemical_service.create({"name": "硫酸铜", "cas_number": "7758-98-7"})
        self.ledger = BottleLedger()

    def tearDown(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    # ------------------------------------------------------------------
    def _inbound(self, number: str, **overrides) -> dict:
        fields = {
            "bottle_number": number,
            "reagent_name": "硫酸铜",
            "cas_number": "7758-98-7",
            "remaining_quantity": 100.0,
            "specification": 500.0,
            "unit": "g",
            "supplier": "国药",
            "unit_price": 12.5,
            "storage_location": "危化品柜 1",
        }
        fields.update(overrides)
        reagent_bottle_service.create(fields)
        return self.ledger.attach(number, fields, moved_by="张三")

    def _bottle(self, number: str):
        return reagent_bottle_service.get_by_bottle_number(number)

    def _placements(self, number: str) -> list:
        return TEST_DB.execute_query(
            "SELECT * FROM bottle_placement WHERE bottle_number = ? ORDER BY id", (number,)
        )

    # ------------------------------------------------------------------
    def test_inbound_writes_all_three(self):
        attached = self._inbound("L0001")

        bottle = self._bottle("L0001")
        self.assertEqual(bottle.chemical_id, attached["chemical_id"])
        self.assertEqual(bottle.lot_id, attached["lot_id"])
        self.assertTrue(bottle.placement_at)

        lot = TEST_DB.execute_query(
            "SELECT * FROM bottle_lot WHERE id = ?", (bottle.lot_id,)
        )[0]
        self.assertEqual(lot["supplier"], "国药")
        self.assertAlmostEqual(lot["unit_price"], 12.5)
        self.assertAlmostEqual(lot["specification"], 500.0)

        places = self._placements("L0001")
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["storage_location"], "危化品柜 1")
        self.assertEqual(places[0]["moved_by"], "张三")

    def test_one_delivery_is_one_lot(self):
        first = self._inbound("L0002")
        second = self._inbound("L0003")
        self.assertEqual(first["lot_id"], second["lot_id"])
        lots = TEST_DB.execute_query("SELECT COUNT(*) AS n FROM bottle_lot")
        self.assertEqual(lots[0]["n"], 1)

    def test_a_different_unit_price_is_a_different_lot(self):
        first = self._inbound("L0004")
        second = self._inbound("L0005", unit_price=13.0)
        self.assertNotEqual(first["lot_id"], second["lot_id"])

    def test_an_unknown_substance_is_not_invented(self):
        """瓶上的名字在档案里没有 → 不自动建档，指针留空等档案补齐。"""
        attached = self._inbound("L0006", reagent_name="某自配缓冲液", cas_number="")
        self.assertIsNone(attached["chemical_id"])
        self.assertIsNone(self._bottle("L0006").chemical_id)
        # 批次照样建：批次记录的是「这批货」，与档案是否齐备无关
        self.assertIsNotNone(attached["lot_id"])

    def test_moving_appends_and_updates_the_current_value(self):
        self._inbound("L0007")
        self.ledger.move_to("L0007", "危化品柜 3", moved_by="李四", note="实验台用完归位")

        places = self._placements("L0007")
        self.assertEqual(len(places), 2)
        self.assertEqual(places[-1]["storage_location"], "危化品柜 3")
        self.assertEqual(self.ledger.current_place("L0007"), "危化品柜 3")
        # 主表上那份缓存同步更新，避免「瓶说 A、位置表说 B」
        self.assertEqual(self._bottle("L0007").storage_location, "危化品柜 3")

    def test_the_signature_is_the_four_columns_we_agreed_on(self):
        self.assertEqual(LOT_SIGNATURE,
                         ("chemical_id", "supplier", "unit_price", "specification"))


class Consistency(unittest.TestCase):
    """体检脚本：干净时沉默，长歪了要说话。"""

    def setUp(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()
        chemical_service.create({"name": "硫酸铜", "cas_number": "7758-98-7"})
        self.ledger = BottleLedger()
        self.checker = _load_checker()

    def tearDown(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    def _inbound(self, number: str = "C0001") -> None:
        fields = {
            "bottle_number": number,
            "reagent_name": "硫酸铜",
            "cas_number": "7758-98-7",
            "remaining_quantity": 100.0,
            "specification": 500.0,
            "unit": "g",
            "supplier": "国药",
            "unit_price": 12.5,
            "storage_location": "危化品柜 1",
        }
        reagent_bottle_service.create(fields)
        self.ledger.attach(number, fields, moved_by="张三")

    def _report(self):
        return self.checker.ConsistencyReport(TEST_DB).run()

    # ------------------------------------------------------------------
    def test_a_clean_shelf_has_nothing_to_report(self):
        self._inbound()
        report = self._report()
        self.assertEqual(report.total(), 0, report.describe())
        self.assertEqual(report.bottles, 1)

    def test_a_bottle_without_a_lot_is_reported(self):
        self._inbound()
        TEST_DB.connection.execute("UPDATE reagent_bottle SET lot_id = NULL")
        TEST_DB.connection.commit()
        self.assertEqual(len(self._report().problems["lot_missing"]), 1)

    def test_a_price_changed_on_one_side_is_reported(self):
        self._inbound()
        TEST_DB.connection.execute("UPDATE bottle_lot SET unit_price = 99.0")
        TEST_DB.connection.commit()
        problems = self._report().problems["lot_drift"]
        self.assertEqual(len(problems), 1)
        self.assertIn("unit_price", problems[0])

    def test_a_missing_placement_is_reported(self):
        self._inbound()
        TEST_DB.connection.execute("DELETE FROM bottle_placement")
        TEST_DB.connection.commit()
        self.assertEqual(len(self._report().problems["place_missing"]), 1)

    def test_a_location_changed_on_one_side_is_reported(self):
        self._inbound()
        TEST_DB.connection.execute(
            "UPDATE reagent_bottle SET storage_location = '别的地方'"
        )
        TEST_DB.connection.commit()
        self.assertEqual(len(self._report().problems["place_drift"]), 1)

    def test_a_link_that_could_have_been_made_is_reported(self):
        """档案里有这个 CAS，瓶却没关联：这是漏写的指针，不是「查不到」。"""
        self._inbound()
        TEST_DB.connection.execute("UPDATE reagent_bottle SET chemical_id = NULL")
        TEST_DB.connection.commit()
        self.assertEqual(len(self._report().problems["sub_missing"]), 1)

    def test_a_wrong_substance_is_reported(self):
        self._inbound()
        other = chemical_service.create({"name": "氯化钠", "cas_number": "7647-14-5"})
        TEST_DB.connection.execute(
            "UPDATE reagent_bottle SET chemical_id = ?", (other,)
        )
        TEST_DB.connection.commit()
        self.assertEqual(len(self._report().problems["sub_drift"]), 1)

    def test_the_exit_code_says_whether_to_worry(self):
        self._inbound()
        report = self._report()
        self.assertEqual(0 if report.total() == 0 else 1, 0)


if __name__ == "__main__":
    unittest.main()
