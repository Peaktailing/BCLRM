"""查询层可借性二次过滤与 sync_all 修正集成测试（隔离临时库）。

覆盖：
- 存量脏行（borrowable_check=1 但已过期）被 borrowable_only 查询过滤；
- sync_all 顺带修正存量脏行；
- 报废瓶不入可借列表；
- 恢复正常不误放「已借出」瓶。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.query_service import query_service
from business.expiry_service import expiry_service
from services.core.reagent_bottle_service import reagent_bottle_service
from utils.id_generator import id_generator

_TABLES = ("reagent_bottle", "chemical_info")


class TestQueryBorrowableFilter(unittest.TestCase):
    def setUp(self):
        for t in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    def tearDown(self):
        for t in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    def _make_bottle(self, **fields) -> str:
        bn = id_generator.generate_bottle_number()
        data = {
            "bottle_number": bn,
            "reagent_name": "测试试剂",
            "cas_number": "123-45-6",
            "remaining_quantity": 100.0,
            "borrowable_flag": "可借",
            "expired_flag": "正常",
        }
        data.update(fields)
        reagent_bottle_service.create(data)
        return bn

    def _fetch(self, bn):
        return reagent_bottle_service.get_by_bottle_number(bn)

    def test_dirty_expired_row_filtered_by_borrowable_only(self):
        """存量脏行（check=1 + 已过期）不得出现在 borrowable_only 结果中。"""
        dirty = self._make_bottle(
            expired_flag="已过期",
            borrowable_check=1,
            production_date="2020/01/01",  # 确实已过期（默认有效期 730 天）
        )
        normal = self._make_bottle()

        result = query_service.search_reagents(borrowable_only=True)
        self.assertTrue(result.is_success(), result.message)
        numbers = [b.bottle_number for b in result.data]
        self.assertNotIn(dirty, numbers, "已过期脏行不得出现在可借列表")
        self.assertIn(normal, numbers)

    def test_sync_all_fixes_dirty_check(self):
        """sync_all 应修正 check=1 但已过期的存量脏行。"""
        dirty = self._make_bottle(
            expired_flag="已过期",
            borrowable_check=1,
            production_date="2020/01/01",
        )
        result = expiry_service.sync_all()
        self.assertTrue(result.is_success(), result.message)
        row = self._fetch(dirty)
        self.assertEqual(row.expired_flag, "已过期")
        self.assertFalse(bool(row.borrowable_check), "sync_all 应将过期瓶 check 置 0")

    def test_scrapped_bottle_not_in_borrowable_list(self):
        """报废瓶（含存量脏 check=1）不入可借列表。"""
        scrapped = self._make_bottle(
            scrap_flag="待报废",
            borrowable_flag="空瓶",
            borrowable_check=1,  # 脏值
            remaining_quantity=0.0,
        )
        scrapped2 = self._make_bottle(
            scrap_flag="已报废",
            borrowable_check=1,  # 脏值
        )
        result = query_service.search_reagents(borrowable_only=True)
        self.assertTrue(result.is_success(), result.message)
        numbers = [b.bottle_number for b in result.data]
        self.assertNotIn(scrapped, numbers)
        self.assertNotIn(scrapped2, numbers)

        # sync_all 顺带修正报废瓶脏 check
        expiry_service.sync_all()
        for bn in (scrapped, scrapped2):
            self.assertFalse(bool(self._fetch(bn).borrowable_check))

    def test_restored_normal_keeps_borrowed_bottle_locked(self):
        """过期恢复正常时，「已借出」瓶不得被误置为可借。

        构造：库存标已过期（脏值），但按生产日期判断实际未过期（恢复分支），
        且瓶处于「已借出」——sync_all 恢复过期状态时不得置 check=1。
        """
        borrowed = self._make_bottle(
            borrowable_flag="已借出",
            expired_flag="已过期",
            borrowable_check=0,
            production_date="2099/01/01",
        )
        result = expiry_service.sync_all()
        self.assertTrue(result.is_success(), result.message)
        row = self._fetch(borrowed)
        self.assertEqual(row.expired_flag, "正常", "sync_all 应将过期脏值恢复为正常")
        self.assertFalse(
            bool(row.borrowable_check),
            "已借出瓶恢复过期状态后不得被误置为可借",
        )


if __name__ == "__main__":
    unittest.main()
