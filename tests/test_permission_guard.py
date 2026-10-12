"""服务端写权限守卫（utils/permission_guard.py）单元测试"""
import unittest

from utils.error_handler import PermissionDeniedError
from utils.permission_guard import enforce_write
from utils.user_context import set_user, clear_user


class TestPermissionGuard(unittest.TestCase):
    """集中式写权限守卫规则"""

    def tearDown(self):
        clear_user()

    def test_no_context_allows_write(self):
        """无上下文（脚本/测试/初始化）放行"""
        clear_user()
        enforce_write("person", {"name": "x"}, action="新增")
        enforce_write("person", action="删除")

    def test_user_blocked_on_person_table(self):
        """普通用户写 person 表被拒"""
        set_user("张三", "user")
        with self.assertRaises(PermissionDeniedError):
            enforce_write("person", {"role": "super_admin"}, action="更新")
        with self.assertRaises(PermissionDeniedError):
            enforce_write("person", action="删除")

    def test_user_blocked_on_controlled_list(self):
        """普通用户写管控名录被拒"""
        set_user("张三", "teacher")
        with self.assertRaises(PermissionDeniedError):
            enforce_write("controlled_list", {"name": "丙酮"}, action="新增")

    def test_user_blocked_on_approval_status(self):
        """普通用户写审批状态字段被拒（任何表）"""
        set_user("张三", "user")
        with self.assertRaises(PermissionDeniedError):
            enforce_write("borrow_order", {"approval_status": "已批准"}, action="更新")
        with self.assertRaises(PermissionDeniedError):
            enforce_write("purchase_plan", {"approval_status": "已驳回"}, action="更新")

    def test_user_allowed_on_normal_fields(self):
        """普通用户正常业务写入放行（不误伤领用/归还/课程）"""
        set_user("张三", "user")
        enforce_write("borrow_order", {"status": "借用中"}, action="更新")
        enforce_write("borrow_order_item", {"borrow_qty": 10}, action="更新")
        enforce_write("experiment_usage", {"usage": 5}, action="新增")
        enforce_write("chemical_info", {"msds": "a.pdf"}, action="更新")

    def test_admin_allowed_everywhere(self):
        """管理员及以上全部放行"""
        for role in ("admin", "super_admin"):
            set_user("李四", role)
            enforce_write("person", {"role": "admin"}, action="更新")
            enforce_write("borrow_order", {"approval_status": "已批准"}, action="更新")
            enforce_write("controlled_list", action="删除")


if __name__ == "__main__":
    unittest.main()
