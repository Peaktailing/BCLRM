"""写入版本（rev）：谁都能读，只有读到的那一版能写。

一个试剂瓶的写入路径原本是「读 → 判断 → 写」，两步之间另一路写入完全
可以插进来：同一瓶被两个人同时流转管理权、审批进行中申请人撤回。状态
条件更新（update_where）防住了「状态被改」，防不住「状态没变但值变了」
——管理人被换成了别人，瓶子依旧是可借。

rev 是唯一一个每次写入都动的字段，因此它同时是「有没有人动过」的判据。
本文件确认四件事：

1. 每种写入都推进版本（update / update_by_field / update_where / 借 / 还）
2. 点名版本写入时，版本不符就拒绝，且一个字节都没改
3. expect=None 不校验（导入与批量作业的逃生口）
4. 业务方法自己读、自己写的那段窗口（管理权流转）真的会被拦住
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.borrow_service import borrow_service
from business.manager_service import manager_service
from business.return_service import return_service
from services.base.person_service import person_service
from services.core.reagent_bottle_service import reagent_bottle_service
from utils.error_handler import StaleRevisionError
from utils.field_mapper import ReagentBottleField
from utils.id_generator import id_generator

_TABLES = (
    "borrow_record", "return_record", "manager_change_log",
    "reagent_bottle", "chemical_info", "reagent_type", "person", "daily_counters",
)


def _bump_out_of_band(bottle_number: str) -> None:
    """模拟「另一个会话改了这瓶」：绕过服务直接推进版本。

    真实世界那一路可能是另一个 Streamlit 实例，或一段导入脚本；它们都
    不会经过本进程的事务锁，正是 rev 要挡住的那种写入。
    """
    TEST_DB.connection.execute(
        "UPDATE reagent_bottle SET rev = rev + 1 WHERE bottle_number = ?", (bottle_number,)
    )
    TEST_DB.connection.commit()


class Revision(unittest.TestCase):
    """一瓶一号，一写一版。"""

    def setUp(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()
        for name in ("流转甲", "流转乙", "流转丙"):
            person_service.create({"name": name, "role": "admin"})

    def tearDown(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    # ------------------------------------------------------------------
    def _a_bottle(self, remaining: float = 100.0, manager: str = "流转甲") -> str:
        number = id_generator.generate_bottle_number()
        reagent_bottle_service.create({
            "bottle_number": number,
            "reagent_name": "版本测试试剂",
            "remaining_quantity": remaining,
            "unit": "g",
            "borrowable_flag": "可借",
            "borrowable_check": 1,
            "expired_flag": "正常",
            "manager": manager,
        })
        return number

    def _rev(self, number: str) -> int:
        bottle = reagent_bottle_service.get_by_bottle_number(number)
        return int(bottle.rev or 0)

    # ------------------------------------------------------------------
    # 1. 每次写入都推进版本
    # ------------------------------------------------------------------
    def test_a_new_bottle_starts_at_zero(self):
        self.assertEqual(self._rev(self._a_bottle()), 0)

    def test_update_bumps_the_version(self):
        number = self._a_bottle()
        reagent_bottle_service.update(
            reagent_bottle_service.get_by_bottle_number(number).id,
            {ReagentBottleField.PURITY: "分析纯"},
        )
        self.assertEqual(self._rev(number), 1)

    def test_update_by_field_bumps_the_version(self):
        number = self._a_bottle()
        reagent_bottle_service.update_by_field(
            ReagentBottleField.BOTTLE_NUMBER, number,
            {ReagentBottleField.EXPIRED_FLAG: "即将过期"},
        )
        self.assertEqual(self._rev(number), 1)

    def test_condition_update_bumps_the_version(self):
        number = self._a_bottle()
        bottle = reagent_bottle_service.get_by_bottle_number(number)
        reagent_bottle_service.update_where(
            {ReagentBottleField.ID: bottle.id,
             ReagentBottleField.REMAINING_QUANTITY: 100.0},
            {ReagentBottleField.REMAINING_QUANTITY: 96.0},
        )
        self.assertEqual(self._rev(number), 1)

    def test_a_borrow_and_a_return_each_bump_the_version(self):
        number = self._a_bottle()
        borrow_service.reagent_borrow(number, "测试用户", 10.0)
        after_borrow = self._rev(number)
        self.assertGreater(after_borrow, 0)
        return_service.reagent_return(number, "测试用户", 90.0)
        self.assertGreater(self._rev(number), after_borrow)

    def test_the_version_cannot_be_set_by_hand(self):
        """调用方塞进 fields 的 rev 会被丢掉：版本只由服务推进。"""
        number = self._a_bottle()
        bottle = reagent_bottle_service.get_by_bottle_number(number)
        reagent_bottle_service.update(
            bottle.id,
            {ReagentBottleField.PURITY: "化学纯", ReagentBottleField.REV: 99},
        )
        self.assertEqual(self._rev(number), 1)

    # ------------------------------------------------------------------
    # 2. 点名版本：不符就拒绝，且不改任何东西
    # ------------------------------------------------------------------
    def test_the_version_it_read_is_accepted(self):
        number = self._a_bottle()
        bottle = reagent_bottle_service.get_by_bottle_number(number)
        written = reagent_bottle_service.update(
            bottle.id,
            {ReagentBottleField.PURITY: "分析纯"},
            expect_rev=bottle.rev,
        )
        self.assertTrue(written)
        self.assertEqual(self._rev(number), 1)

    def test_a_version_that_moved_on_is_refused(self):
        number = self._a_bottle()
        bottle = reagent_bottle_service.get_by_bottle_number(number)   # 读到第 0 版
        _bump_out_of_band(number)                                      # 别人改成第 1 版

        with self.assertRaises(StaleRevisionError) as caught:
            reagent_bottle_service.update(
                bottle.id,
                {ReagentBottleField.PURITY: "分析纯"},
                expect_rev=bottle.rev,
            )
        self.assertIn("已被改动", str(caught.exception))
        self.assertEqual(caught.exception.details["expected"], 0)
        self.assertEqual(caught.exception.details["current"], 1)

        # 拒绝 = 一个字节都没写：纯度仍是空，版本也没再涨
        after = reagent_bottle_service.get_by_bottle_number(number)
        self.assertFalse(after.purity)
        self.assertEqual(int(after.rev), 1)

    def test_a_refused_write_by_field_also_changes_nothing(self):
        number = self._a_bottle()
        _bump_out_of_band(number)
        with self.assertRaises(StaleRevisionError):
            reagent_bottle_service.update_by_field(
                ReagentBottleField.BOTTLE_NUMBER, number,
                {ReagentBottleField.EXPIRED_FLAG: "已过期"},
                expect_rev=0,
            )
        self.assertEqual(
            reagent_bottle_service.get_by_bottle_number(number).expired_flag, "正常"
        )

    def test_no_version_means_no_comparison(self):
        """expect=None 是给导入与批量作业的：读都没读，就没有可比的东西。"""
        number = self._a_bottle()
        bottle = reagent_bottle_service.get_by_bottle_number(number)
        _bump_out_of_band(number)
        written = reagent_bottle_service.update(
            bottle.id, {ReagentBottleField.PURITY: "分析纯"}
        )
        self.assertTrue(written)
        self.assertEqual(self._rev(number), 2)

    def test_a_missing_row_is_not_a_version_conflict(self):
        """行没了不是版本问题：沿用既有语义返回 False，不抛 StaleRevisionError。"""
        written = reagent_bottle_service.update(
            999999, {ReagentBottleField.PURITY: "分析纯"}, expect_rev=0
        )
        self.assertFalse(written)

    # ------------------------------------------------------------------
    # 3. 业务方法自己的读—写窗口
    # ------------------------------------------------------------------
    def test_a_transfer_is_refused_when_the_bottle_moved_between_read_and_write(self):
        """管理权流转读一次、写一次；中间有人先流转了，第二次必须失败。

        这是 rev 存在的理由：状态条件更新拦不住它（两边的瓶都是「可借」），
        只有版本能说明「我读到的那瓶已经不在了」。
        """
        number = self._a_bottle(manager="流转甲")
        seen = reagent_bottle_service.get_by_bottle_number(number)   # 业务读到的第 0 版

        # 另一个会话抢先把管理人改成「流转乙」
        _bump_out_of_band(number)
        reagent_bottle_service.update(
            seen.id, {ReagentBottleField.MANAGER: "流转乙"}
        )
        # 此时库里是第 2 版、管理人是乙；手里那一份仍写着甲

        with mock.patch.object(
            manager_service.bottle_service, "get_by_bottle_number", return_value=seen
        ):
            result = manager_service.transfer(number, "流转丙", "操作人")

        self.assertFalse(result.is_success(), result.message)
        self.assertEqual(result.error_code, "STALE_REVISION")
        # 没有被覆盖：库里仍是乙，不是丙
        self.assertEqual(
            reagent_bottle_service.get_by_bottle_number(number).manager, "流转乙"
        )
        # 也没有留下流转记录（同事务回滚：瓶没改，日志也不该有）
        rows = TEST_DB.execute_query(
            "SELECT COUNT(*) AS n FROM manager_change_log WHERE bottle_number = ?", (number,)
        )
        self.assertEqual(rows[0]["n"], 0)

    def test_a_transfer_on_a_fresh_read_still_works(self):
        """加版本不等于加摩擦：没人抢的时候照常成功。"""
        number = self._a_bottle(manager="流转甲")
        result = manager_service.transfer(number, "流转乙", "操作人")
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(
            reagent_bottle_service.get_by_bottle_number(number).manager, "流转乙"
        )


if __name__ == "__main__":
    unittest.main()
