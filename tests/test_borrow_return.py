"""borrow/return 状态流转与事务原子性集成测试（隔离临时库）。

隔离由 tests/__init__.py 保证：导入本模块前全局 Database 单例已指向临时库，
因此所有建表/插入/查询都在临时库进行，不触碰真实 db/main.db。
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.borrow_service import borrow_service
from business.return_service import return_service
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.borrow_record_service import borrow_record_service
from services.core.return_record_service import return_record_service
from utils.id_generator import id_generator

# 清理顺序：先子表后父表（避免外键约束）
_TABLES = (
    "borrow_record", "return_record", "reagent_bottle",
    "chemical_info", "reagent_type", "person", "daily_counters",
)


class TestBorrowReturnFlow(unittest.TestCase):
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

    def _make_bottle(self, borrowable="可借", expired="正常", remaining=100.0):
        bn = id_generator.generate_bottle_number()
        reagent_bottle_service.create({
            "bottle_number": bn,
            "reagent_name": "测试试剂",
            "cas_number": "123-45-6",
            "remaining_quantity": remaining,
            "borrowable_flag": borrowable,
            "expired_flag": expired,
        })
        return bn

    def test_borrow_success_updates_state(self):
        bn = self._make_bottle()
        result = borrow_service.reagent_borrow(bn, "测试用户", 10.0)
        self.assertTrue(result.is_success(), result.message)

        b = reagent_bottle_service.get_by_bottle_number(bn)
        self.assertEqual(b.borrowable_flag, "已借出")
        self.assertAlmostEqual(float(b.remaining_quantity), 90.0)

        recs = borrow_record_service.get_by_bottle_number(bn)
        self.assertEqual(len(recs), 1)

    def test_return_success_restores_state(self):
        bn = self._make_bottle()
        borrow_service.reagent_borrow(bn, "u", 10.0)
        result = return_service.reagent_return(bn, "u", 90.0)
        self.assertTrue(result.is_success(), result.message)

        b = reagent_bottle_service.get_by_bottle_number(bn)
        self.assertEqual(b.borrowable_flag, "可借")
        self.assertAlmostEqual(float(b.remaining_quantity), 90.0)

        returns = return_record_service.get_by_bottle_number(bn)
        self.assertEqual(len(returns), 1)
        ret = returns[0]

        # 修复后：归还必须回填关联领用记录的归还号，保证借还状态一致。
        # 注：BorrowRecord 模型未映射 linked_return_record_number，改用底层字典读取。
        borrow_row = borrow_record_service.get_by_field("bottle_number", bn)
        return_row = return_record_service.get_by_field("bottle_number", bn)
        self.assertIsNotNone(borrow_row)
        self.assertIsNotNone(return_row)
        self.assertEqual(
            borrow_row["linked_return_record_number"],
            return_row["return_number"],
        )

    def test_borrow_rejects_not_borrowable(self):
        bn = self._make_bottle(borrowable="已借出")
        result = borrow_service.reagent_borrow(bn, "u", 5.0)
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "BOTTLE_NOT_BORROWABLE")

    def test_borrow_rollback_on_bottle_update_failure(self):
        """事务原子性：库存更新失败时，领用记录必须随事务整体回滚（无孤儿记录）。"""
        bn = self._make_bottle()
        with mock.patch.object(
            reagent_bottle_service, "update", side_effect=RuntimeError("boom")
        ):
            result = borrow_service.reagent_borrow(bn, "u", 5.0)

        self.assertTrue(result.is_failure())
        recs = borrow_record_service.get_by_bottle_number(bn)
        self.assertEqual(len(recs), 0, "领用记录应被回滚，不应留下孤儿记录")

    def test_return_rollback_when_borrow_link_update_fails(self):
        """事务原子性：关联领用记录更新失败（记录仍存在）应回滚整个归还，与瓶更新一致。"""
        bn = self._make_bottle()
        borrow_service.reagent_borrow(bn, "u", 10.0)
        with mock.patch.object(
            borrow_record_service, "update", return_value=False
        ), mock.patch.object(
            borrow_record_service, "get_by_id", return_value={"id": 1}
        ):
            result = return_service.reagent_return(bn, "u", 90.0)

        self.assertTrue(result.is_failure(), result.message)
        self.assertEqual(
            len(return_record_service.get_by_bottle_number(bn)),
            0,
            "关联更新失败应触发事务回滚，归还记录不应留下",
        )

    def test_return_skips_missing_borrow_record(self):
        """关联领用记录已不存在（已删除）属合法情况，应跳过关联并正常完成归还。"""
        bn = self._make_bottle()
        borrow_service.reagent_borrow(bn, "u", 10.0)
        with mock.patch.object(
            borrow_record_service, "update", return_value=False
        ), mock.patch.object(
            borrow_record_service, "get_by_id", return_value=None
        ):
            result = return_service.reagent_return(bn, "u", 90.0)

        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(len(return_record_service.get_by_bottle_number(bn)), 1)
        b = reagent_bottle_service.get_by_bottle_number(bn)
        self.assertEqual(b.borrowable_flag, "可借")

    def test_return_rejects_qty_exceeding_borrow_total(self):
        """归还量不得超过借出时的总量（借出后剩余 + 领用量）。"""
        bn = self._make_bottle()                       # 瓶内 100
        borrow_service.reagent_borrow(bn, "u", 10.0)   # -> 90，借出时总量 100
        result = return_service.reagent_return(bn, "u", 105.0)
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "RETURN_QTY_EXCEEDS_BORROW")
        # 校验失败不应改动库存
        b = reagent_bottle_service.get_by_bottle_number(bn)
        self.assertEqual(b.borrowable_flag, "已借出")
        self.assertAlmostEqual(float(b.remaining_quantity), 90.0)

    def test_return_allows_qty_within_borrow_total(self):
        """归还量等于借出时总量（全部还回）应允许。"""
        bn = self._make_bottle()
        borrow_service.reagent_borrow(bn, "u", 10.0)
        result = return_service.reagent_return(bn, "u", 100.0)
        self.assertTrue(result.is_success(), result.message)
        b = reagent_bottle_service.get_by_bottle_number(bn)
        self.assertAlmostEqual(float(b.remaining_quantity), 100.0)

    def test_borrow_records_quantity(self):
        """借出时应记录领用量，供归还校验使用。"""
        bn = self._make_bottle()
        borrow_service.reagent_borrow(bn, "u", 10.0)
        row = borrow_record_service.get_by_field("bottle_number", bn)
        self.assertIsNotNone(row)
        self.assertAlmostEqual(float(row["borrow_quantity"]), 10.0)


if __name__ == "__main__":
    unittest.main()
