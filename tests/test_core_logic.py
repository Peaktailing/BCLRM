"""核心逻辑单元测试（零依赖，使用 unittest，不触碰真实数据库）

覆盖：
- 密码哈希往返（utils.security）
- 业务结果包装契约（utils.error_handler.ServiceResult）
- 过期状态计算（business.expiry_service.check_bottle，纯计算，用 chemical_cache 绕过 DB）

说明：check_bottle 是纯函数式计算，给定 bottle + chemical_cache 即可判定，
无需连接数据库，因此可作为不依赖 DB 的回归守护。
"""
import sys
import os
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import hash_password, verify_password
from utils.error_handler import ServiceResult
from business.expiry_service import ExpiryService
from models.core.reagent_bottle import ReagentBottle


class TestSecurity(unittest.TestCase):
    def test_hash_verify_roundtrip(self):
        h = hash_password("secret123")
        self.assertTrue(verify_password("secret123", h))
        self.assertFalse(verify_password("wrong", h))

    def test_hash_unique_salt(self):
        # 相同明文每次哈希结果不同（随机盐），但均可通过校验
        h1 = hash_password("x")
        h2 = hash_password("x")
        self.assertNotEqual(h1, h2)
        self.assertTrue(verify_password("x", h1))
        self.assertTrue(verify_password("x", h2))


class TestServiceResult(unittest.TestCase):
    def test_ok_and_success(self):
        r = ServiceResult.ok(data={"a": 1})
        self.assertTrue(r.is_success())
        self.assertEqual(r.data, {"a": 1})

    def test_fail_and_failure(self):
        r = ServiceResult.fail("boom", error_code="E1")
        self.assertFalse(r.is_success())
        self.assertTrue(r.is_failure())
        self.assertEqual(r.error_code, "E1")


class TestExpiryLogic(unittest.TestCase):
    """check_bottle 是纯计算：给定 bottle + chemical_cache 即可判定，无需 DB。"""

    def _make_bottle(self, unseal_date=None, production_date="2020/01/01"):
        return ReagentBottle(
            bottle_number="TEST0001",
            reagent_name="TestChem",
            cas_number="123-45-6",
            production_date=production_date,
            unseal_date=unseal_date,
        )

    def _cache(self, unsealed, sealed):
        return {
            "name:TestChem": SimpleNamespace(
                unsealed_shelf_life=unsealed, sealed_shelf_life=sealed
            )
        }

    def test_unsealed_expired(self):
        # 很久以前生产、未启封、有效期 1 天 -> 已过期
        b = self._make_bottle(unseal_date=None, production_date="2000/01/01")
        cache = self._cache(unsealed=1, sealed=365)
        self.assertEqual(ExpiryService().check_bottle(b, cache), "已过期")

    def test_sealed_expired(self):
        # 启封于很久以前、启封有效期 1 天 -> 已过期
        b = self._make_bottle(unseal_date="2000/01/01")
        cache = self._cache(unsealed=365, sealed=1)
        self.assertEqual(ExpiryService().check_bottle(b, cache), "已过期")

    def test_normal(self):
        # 远期生产、未启封、长有效期 -> 正常
        b = self._make_bottle(unseal_date=None, production_date="2099/01/01")
        cache = self._cache(unsealed=365, sealed=365)
        self.assertEqual(ExpiryService().check_bottle(b, cache), "正常")


class TestExpiryNoNPlusOne(unittest.TestCase):
    """验证 get_expiry_stats 不再对每瓶单独查询化学品表（N+1 已消除）。"""

    def test_no_per_bottle_chemical_query(self):
        from unittest import mock
        from types import SimpleNamespace

        fake_chem = SimpleNamespace(
            name="ChemA", cas_number="111-11-1",
            unsealed_shelf_life=365, sealed_shelf_life=365,
        )
        fake_bottle = ReagentBottle(
            bottle_number="B1", reagent_name="ChemA",
            cas_number="111-11-1", production_date="2099/01/01",
        )
        svc = ExpiryService()
        chem_mock = mock.MagicMock()
        bot_mock = mock.MagicMock()
        chem_mock.get_all_parsed.return_value = [fake_chem]
        bot_mock.get_all_parsed.return_value = [fake_bottle]
        svc.chemical_service = chem_mock
        svc.bottle_service = bot_mock

        result = svc.get_expiry_stats()

        # 关键断言：check_bottle 应使用缓存，而不是逐瓶查询化学品表
        chem_mock.get_by_name.assert_not_called()
        chem_mock.get_by_cas_number.assert_not_called()
        self.assertTrue(result.is_success())
        self.assertEqual(result.data["normal"], 1)


if __name__ == "__main__":
    unittest.main()
