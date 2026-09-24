"""试剂瓶状态机单元测试。

验证 borrowable_flag / expired_flag 的取值与判定逻辑收敛到单一模块，
保证各业务入口（借出、归还、入库、查询）使用一致的规则。
"""
import unittest

from business.bottle_state import (
    BorrowableStatus,
    ExpiryStatus,
    borrowable_flag_on_borrow,
    borrowable_flag_on_inbound,
    borrowable_flag_on_return,
    is_borrowable,
    is_expired,
)


class TestBorrowableStatusEnum(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual(BorrowableStatus.BORROWABLE.value, "可借")
        self.assertEqual(BorrowableStatus.BORROWED.value, "已借出")
        self.assertEqual(BorrowableStatus.DEPLETED.value, "耗尽")

    def test_expiry_status_values(self):
        self.assertEqual(ExpiryStatus.NORMAL.value, "正常")
        self.assertEqual(ExpiryStatus.EXPIRING.value, "即将过期")
        self.assertEqual(ExpiryStatus.EXPIRED.value, "已过期")


class TestBorrowableFlagComputation(unittest.TestCase):
    def test_on_borrow_is_fixed(self):
        self.assertEqual(borrowable_flag_on_borrow(), "已借出")

    def test_on_inbound_positive_qty(self):
        self.assertEqual(borrowable_flag_on_inbound(10.0), "可借")

    def test_on_inbound_zero_qty(self):
        self.assertEqual(borrowable_flag_on_inbound(0.0), "耗尽")

    def test_on_inbound_negative_qty(self):
        self.assertEqual(borrowable_flag_on_inbound(-1.0), "耗尽")

    def test_on_return_positive_qty(self):
        self.assertEqual(borrowable_flag_on_return(5.0), "可借")

    def test_on_return_zero_qty(self):
        self.assertEqual(borrowable_flag_on_return(0.0), "耗尽")

    def test_inbound_and_return_share_rule(self):
        for qty in (100.0, 1.0, 0.0, -3.0):
            self.assertEqual(
                borrowable_flag_on_inbound(qty), borrowable_flag_on_return(qty)
            )


class TestBorrowablePredicates(unittest.TestCase):
    def test_is_borrowable_only_for_borrowable(self):
        self.assertTrue(is_borrowable("可借"))
        self.assertFalse(is_borrowable("已借出"))
        self.assertFalse(is_borrowable("耗尽"))
        self.assertFalse(is_borrowable(None))
        self.assertFalse(is_borrowable(""))

    def test_is_expired_only_for_expired(self):
        self.assertTrue(is_expired("已过期"))
        self.assertFalse(is_expired("正常"))
        self.assertFalse(is_expired("即将过期"))
        self.assertFalse(is_expired(None))


if __name__ == "__main__":
    unittest.main()
