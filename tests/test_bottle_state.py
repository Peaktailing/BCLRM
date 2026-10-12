"""试剂瓶状态机单元测试。

验证 borrowable_flag / expired_flag 的取值与判定逻辑收敛到单一模块，
保证各业务入口（借出、归还、入库、查询）使用一致的规则。
"""
import unittest
from types import SimpleNamespace

from business.bottle_state import (
    BorrowableStatus,
    ExpiryStatus,
    borrowable_flag_on_borrow,
    borrowable_flag_on_inbound,
    borrowable_flag_on_return,
    is_borrowable,
    is_borrowable_now,
    is_expired,
    recompute_borrowable,
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


class TestRecomputeBorrowable(unittest.TestCase):
    """量/过期/报废三要素集中重算（recompute_borrowable / is_borrowable_now）。"""

    @staticmethod
    def _bottle(**kw) -> SimpleNamespace:
        defaults = dict(
            remaining_quantity=100.0,
            expired_flag="正常",
            scrap_flag=None,
            borrowable_flag="可借",
        )
        defaults.update(kw)
        return SimpleNamespace(**defaults)

    def test_full_normal_bottle_is_borrowable(self):
        """有量 + 正常 + 未报废 → 可借。"""
        flag, check = recompute_borrowable(self._bottle())
        self.assertEqual(flag, "可借")
        self.assertTrue(check)
        self.assertTrue(is_borrowable_now(self._bottle()))

    def test_zero_qty_is_depleted(self):
        """无量 → 耗尽、不可借。"""
        flag, check = recompute_borrowable(self._bottle(remaining_quantity=0.0))
        self.assertEqual(flag, "耗尽")
        self.assertFalse(check)
        self.assertFalse(is_borrowable_now(self._bottle(remaining_quantity=0.0)))

    def test_expired_bottle_not_borrowable(self):
        """已过期（有量）→ check 必须为 False，不得借出。"""
        b = self._bottle(expired_flag="已过期")
        flag, check = recompute_borrowable(b)
        self.assertFalse(check)
        self.assertFalse(is_borrowable_now(b))

    def test_scrapped_bottle_not_borrowable(self):
        """已报废（有量）→ 不可借。"""
        b = self._bottle(scrap_flag="已报废")
        flag, check = recompute_borrowable(b)
        self.assertFalse(check)
        self.assertFalse(is_borrowable_now(b))

    def test_returned_borrowed_expired_not_revived(self):
        """已借出 + 已过期瓶归还（有量）→ 不得被重设为可借（check=False）。"""
        b = self._bottle(borrowable_flag="已借出", expired_flag="已过期")
        flag, check = recompute_borrowable(b)
        self.assertFalse(check)
        self.assertFalse(is_borrowable_now(b))

    def test_returned_borrowed_scrapped_not_revived(self):
        """已借出 + 待报废瓶归还 → 不得被重设为可借，且转入空瓶态。"""
        b = self._bottle(
            borrowable_flag="已借出", remaining_quantity=0.0, scrap_flag="待报废"
        )
        flag, check = recompute_borrowable(b)
        self.assertEqual(flag, "空瓶")
        self.assertFalse(check)
        self.assertFalse(is_borrowable_now(b))

    def test_expiring_flag_still_borrowable(self):
        """即将过期（未到期）仍可借。"""
        b = self._bottle(expired_flag="即将过期")
        flag, check = recompute_borrowable(b)
        self.assertTrue(check)
        self.assertTrue(is_borrowable_now(b))


if __name__ == "__main__":
    unittest.main()
