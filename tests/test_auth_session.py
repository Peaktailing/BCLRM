"""登出业务会话清理纯函数测试（clear_business_session_state）。

覆盖：
- 业务键（领用清单、需求调配明细等）全部清理；
- 登录态键保留（由登出分支自行清理）；
- 清理结果返回被清理键列表，且可重复调用（幂等）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.auth import clear_business_session_state


class TestClearBusinessSessionState(unittest.TestCase):
    def test_business_keys_cleared(self):
        """领用清单/需求明细/表单草稿等业务键应全部清理。"""
        session = {
            "borrow_cart": [{"bottle_number": "B1"}],
            "dmd_lines": [{"reagent_name": "试剂"}],
            "wo_applicant": "张三",
            "wo_approver": "王管理员",
            "wo_cart_course_key": "测试课程|实验一",
            "barcode_query_input": "B8001",
        }
        removed = clear_business_session_state(session)
        self.assertEqual(session, {}, "业务键应全部清理")
        self.assertEqual(
            removed,
            sorted(["borrow_cart", "dmd_lines", "wo_applicant", "wo_approver",
                    "wo_cart_course_key", "barcode_query_input"]),
        )

    def test_login_keys_preserved(self):
        """登录态键与登录表单键保留（清理由登出分支/登录流程负责）。"""
        session = {
            "logged_in": True,
            "user_name": "王管理员",
            "is_admin": True,
            "user_role": "admin",
            "last_activity": 12345.0,
            "login_attempts": 2,
            "login_locked_until": None,
            "login_user_name": "王管理员",
            "borrow_cart": [{"bottle_number": "B1"}],
        }
        clear_business_session_state(session)
        self.assertEqual(
            session,
            {
                "logged_in": True,
                "user_name": "王管理员",
                "is_admin": True,
                "user_role": "admin",
                "last_activity": 12345.0,
                "login_attempts": 2,
                "login_locked_until": None,
                "login_user_name": "王管理员",
            },
            "仅业务键被清理，登录态键保留",
        )

    def test_idempotent_and_empty_session(self):
        """重复调用幂等；空会话返回空列表。"""
        session = {"borrow_cart": []}
        first = clear_business_session_state(session)
        second = clear_business_session_state(session)
        self.assertEqual(first, ["borrow_cart"])
        self.assertEqual(second, [], "二次调用应无键可清")
        self.assertEqual(clear_business_session_state({}), [])


class TestForcePasswordChange(unittest.TestCase):
    """beta 首登强改密（执行版 D12）：仍用默认密码登录就必须先改密。"""

    @staticmethod
    def _make_user(name: str, password: str):
        from services.base.person_service import person_service
        if not person_service.get_by_name(name):
            person_service.create({"name": name, "role": "user"})
        result = person_service.set_password(name, password)
        assert result.is_success(), result.message
        return person_service

    def test_default_password_login_requires_change(self):
        from config.settings import DEFAULT_INITIAL_PASSWORD
        svc = self._make_user("_force_pw_default", DEFAULT_INITIAL_PASSWORD)
        result = svc.authenticate("_force_pw_default", DEFAULT_INITIAL_PASSWORD)
        self.assertTrue(result.is_success(), result.message)
        self.assertTrue(result.data.must_change_password)

    def test_changed_password_login_does_not_require_change(self):
        from config.settings import DEFAULT_INITIAL_PASSWORD
        svc = self._make_user("_force_pw_changed", DEFAULT_INITIAL_PASSWORD)
        self.assertTrue(svc.set_password("_force_pw_changed", "N3w-pass!").is_success())
        result = svc.authenticate("_force_pw_changed", "N3w-pass!")
        self.assertTrue(result.is_success(), result.message)
        self.assertFalse(result.data.must_change_password)

    def test_persisted_flag_from_beta_reset_forces_change(self):
        """beta_reset 写库的标志位必须生效，改密后自动清零（D12）。"""
        svc = self._make_user("_force_pw_beta", "BETA-onetime-pw")
        self.assertTrue(svc.update_by_field(
            "name", "_force_pw_beta", {"must_change_password": 1}
        ))
        result = svc.authenticate("_force_pw_beta", "BETA-onetime-pw")
        self.assertTrue(result.is_success(), result.message)
        self.assertTrue(result.data.must_change_password)

        self.assertTrue(svc.set_password("_force_pw_beta", "Ch4nged-pw!").is_success())
        again = svc.authenticate("_force_pw_beta", "Ch4nged-pw!")
        self.assertTrue(again.is_success(), again.message)
        self.assertFalse(again.data.must_change_password)


if __name__ == "__main__":
    unittest.main()
