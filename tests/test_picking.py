"""抽卡规则：窗口内的局部最优，以及「少开新瓶」是不是真的做到了。

这些测试只依赖 ``capabilities`` 与 ``domain``，不碰数据库——抽卡是纯计算，
应该在没有任何宿主的环境里就能验证。
"""
from __future__ import annotations

import unittest
from datetime import date, timedelta

from capabilities.circulation.picking import HORIZON_DAYS, ShelfPolicy
from capabilities.supply.stock import ExpiryState, StockLot
from domain.substance import SubstanceRef
from domain.units import Quantity, parse_unit

G = parse_unit("g")
ETHANOL = SubstanceRef.of("乙醇")


def a_bottle(lot_id: str, grams, *, opened_days_ago=None,
             expires_in=None, expiry=ExpiryState.FRESH) -> StockLot:
    today = date.today()
    return StockLot(
        lot_id=lot_id,
        substance=ETHANOL,
        quantity=Quantity(grams, G),
        expiry=expiry,
        expires_on=(today + timedelta(days=expires_in)) if expires_in is not None else None,
        opened_on=(today - timedelta(days=opened_days_ago)) if opened_days_ago is not None else None,
    )


class TestWindow(unittest.TestCase):
    """窗口：当前周 + 下一周。窗口只界定「他要用的量」怎么算。"""

    def test_default_is_two_weeks(self):
        policy = ShelfPolicy()
        start, end = policy.window(date(2026, 10, 23))
        self.assertEqual(start, date(2026, 10, 23))
        self.assertEqual(end, date(2026, 11, 6))
        self.assertEqual((end - start).days, HORIZON_DAYS)

    def test_window_is_configurable(self):
        start, end = ShelfPolicy(horizon_days=7).window(date(2026, 10, 23))
        self.assertEqual(end, date(2026, 10, 30))


class TestLessNewBottles(unittest.TestCase):
    """目标只有一个：能不开新瓶就不开。"""

    def setUp(self):
        self.policy = ShelfPolicy()

    def test_opened_bottle_goes_before_sealed_one(self):
        """两瓶都够时，先动已开封的那瓶——省下的是一整瓶的启用。"""
        sealed = a_bottle("B-SEALED", 100)
        opened = a_bottle("B-OPENED", 120, opened_days_ago=3)

        picks = self.policy.pick([sealed, opened], Quantity(50, G))

        self.assertEqual([p.lot_id for p in picks], ["B-OPENED"])

    def test_sealed_bottle_used_when_no_opened_one_available(self):
        picks = self.policy.pick([a_bottle("B1", 100), a_bottle("B2", 200)], Quantity(50, G))
        self.assertEqual([p.lot_id for p in picks], ["B1"])

    def test_one_bottle_beats_two_when_both_cover(self):
        """需求 30，有 100 的瓶和 35 的瓶：抽 35 的，剩下的更接近清空。"""
        big = a_bottle("B-BIG", 100, opened_days_ago=1)
        small = a_bottle("B-SMALL", 35, opened_days_ago=1)

        picks = self.policy.pick([big, small], Quantity(30, G))

        self.assertEqual([p.lot_id for p in picks], ["B-SMALL"])
        self.assertEqual(len(picks), 1)

    def test_big_bottle_wins_when_it_is_the_only_single_cover(self):
        """60 和 200 都开封，需求 100：抽 200 那瓶，一瓶解决。"""
        picks = self.policy.pick(
            [a_bottle("B-60", 60, opened_days_ago=1), a_bottle("B-200", 200, opened_days_ago=1)],
            Quantity(100, G),
        )
        self.assertEqual([p.lot_id for p in picks], ["B-200"])

    def test_clears_small_bottles_first_when_nothing_covers(self):
        """都不够一瓶时，先清空小的，半瓶数下降得更快。"""
        picks = self.policy.pick(
            [a_bottle("B-60", 60, opened_days_ago=1), a_bottle("B-20", 20, opened_days_ago=1)],
            Quantity(100, G),
        )
        self.assertEqual([p.lot_id for p in picks], ["B-20", "B-60"])

    def test_near_expiry_overrides_new_bottle_saving(self):
        """临期瓶即使未开封也先出：不在窗口内用掉就是报废。"""
        fresh_opened = a_bottle("B-OPENED", 100, opened_days_ago=1)
        near = a_bottle("B-NEAR", 100, expires_in=3, expiry=ExpiryState.EXPIRING)

        picks = self.policy.pick([fresh_opened, near], Quantity(50, G))

        self.assertEqual([p.lot_id for p in picks], ["B-NEAR"])


class TestReserve(unittest.TestCase):
    """「他也够用」是约束：按物质总量留水位，不是按瓶。"""

    def setUp(self):
        self.policy = ShelfPolicy()

    def test_drawable_capped_by_reserve(self):
        """100 的瓶，他要留 60，我只能抽 40——不够 50，返回 40 而不是 50。"""
        picks = self.policy.pick(
            [a_bottle("B1", 100, opened_days_ago=1)],
            Quantity(50, G),
            pool=Quantity(100, G),
            reserved=Quantity(60, G),
        )
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].quantity.base_value(), 40)

    def test_full_reserve_locks_the_shelf(self):
        """他要用的量等于全部存量：一瓶都抽不出来。"""
        picks = self.policy.pick(
            [a_bottle("B1", 100, opened_days_ago=1)],
            Quantity(50, G),
            pool=Quantity(100, G),
            reserved=Quantity(100, G),
        )
        self.assertEqual(picks, ())

    def test_budget_decrements_across_bottles(self):
        """两个 60，他要留 40：最多抽 80，不能每瓶都按「总量−保底」算而超抽。"""
        picks = self.policy.pick(
            [a_bottle("B1", 60, opened_days_ago=1), a_bottle("B2", 60, opened_days_ago=1)],
            Quantity(120, G),
            pool=Quantity(120, G),
            reserved=Quantity(40, G),
        )
        total = sum(p.quantity.base_value() for p in picks)
        self.assertEqual(total, 80)

    def test_reserve_in_another_dimension_is_ignored(self):
        """保底量纲对不上就不锁料——宁可发得出，也不猜折算。"""
        ml = parse_unit("mL")
        picks = self.policy.pick(
            [a_bottle("B1", 100, opened_days_ago=1)],
            Quantity(50, G),
            pool=Quantity(100, G),
            reserved=Quantity(60, ml),
        )
        self.assertEqual(picks[0].quantity.base_value(), 50)

    def test_reserve_defaults_to_none(self):
        picks = self.policy.pick(
            [a_bottle("B1", 100, opened_days_ago=1)], Quantity(50, G)
        )
        self.assertEqual(picks[0].quantity.base_value(), 50)


class TestOrderIsTotal(unittest.TestCase):
    """同输入必须同输出，否则审计对不上。"""

    def setUp(self):
        self.policy = ShelfPolicy()

    def test_identical_bottles_pick_in_stable_order(self):
        lots = [
            a_bottle("B-C", 50, opened_days_ago=1),
            a_bottle("B-A", 50, opened_days_ago=1),
            a_bottle("B-B", 50, opened_days_ago=1),
        ]
        runs = [self.policy.pick(lots, Quantity(120, G)) for _ in range(5)]
        first = [(p.lot_id, p.quantity.base_value()) for p in runs[0]]
        for run in runs[1:]:
            self.assertEqual([(p.lot_id, p.quantity.base_value()) for p in run], first)
        # 全序兜底是瓶号，不依赖传入顺序
        self.assertEqual([p.lot_id for p in runs[0]], ["B-A", "B-B", "B-C"])

    def test_input_order_does_not_matter(self):
        forward = self.policy.pick(
            [a_bottle("B-1", 80, opened_days_ago=1), a_bottle("B-2", 30, opened_days_ago=1)],
            Quantity(20, G),
        )
        backward = self.policy.pick(
            [a_bottle("B-2", 30, opened_days_ago=1), a_bottle("B-1", 80, opened_days_ago=1)],
            Quantity(20, G),
        )
        self.assertEqual([p.lot_id for p in forward], [p.lot_id for p in backward])


class TestShortfall(unittest.TestCase):
    """抽不满就如实返回部分，差额由调用方当缺口处理。"""

    def setUp(self):
        self.policy = ShelfPolicy()

    def test_returns_what_is_there(self):
        picks = self.policy.pick([a_bottle("B1", 30, opened_days_ago=1)], Quantity(100, G))
        total = sum(p.quantity.base_value() for p in picks)
        self.assertEqual(total, 30)

    def test_zero_need_picks_nothing(self):
        self.assertEqual(self.policy.pick([a_bottle("B1", 30)], Quantity(0, G)), ())

    def test_empty_shelf_picks_nothing(self):
        self.assertEqual(self.policy.pick([], Quantity(10, G)), ())

    def test_other_dimension_is_not_used(self):
        ml = parse_unit("mL")
        lot = StockLot(lot_id="B-ML", substance=ETHANOL, quantity=Quantity(100, ml))
        self.assertEqual(self.policy.pick([lot], Quantity(10, G)), ())


class TestBottleRow(unittest.TestCase):
    """开封状态来自 reagent_bottle.unseal_date。"""

    def test_unseal_date_becomes_opened_on(self):
        lot = StockLot.from_bottle_row(
            {
                "bottle_number": "B0001",
                "reagent_name": "乙醇",
                "remaining_quantity": 100,
                "unit": "g",
                "unseal_date": "2026-10-01",
            }
        )
        self.assertEqual(lot.opened_on, date(2026, 10, 1))

    def test_missing_unseal_date_means_sealed(self):
        lot = StockLot.from_bottle_row(
            {
                "bottle_number": "B0002",
                "reagent_name": "乙醇",
                "remaining_quantity": 100,
                "unit": "g",
            }
        )
        self.assertIsNone(lot.opened_on)
        self.assertGreater(ShelfPolicy().order_key(lot, Quantity(10, G))[1], 0)


if __name__ == "__main__":
    unittest.main()
