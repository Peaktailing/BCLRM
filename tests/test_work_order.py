"""领用工单测试（隔离临时库）

覆盖：
- 零星领用 / 课程领用 两种工单的创建与校验
- 工单明细、库存扣减
- 按工单归还：部分归还 → 部分归还；全部归还 → 已归还
- 还入权限（管理员 / 原领用人）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.bottle_state import BorrowableStatus, ScrapStatus
from business.work_order_service import work_order_service
from models.core.borrow_order import (
    ORDER_STATUS_BORROWING,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_RETURNED,
    ORDER_TYPE_COURSE,
    ORDER_TYPE_SPORADIC,
)
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from services.core.borrow_order_service import borrow_order_service
from services.core.borrow_record_service import borrow_record_service
from services.core.reagent_bottle_service import reagent_bottle_service

_TABLES = (
    "borrow_order_item", "borrow_order",
    "borrow_record", "return_record", "reagent_bottle",
    "experiment_item", "experiment_course",
)


class TestWorkOrder(unittest.TestCase):
    def setUp(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    def tearDown(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    # ---------------- 辅助 ----------------
    def _make_bottle(self, bottle_number, reagent_name, remaining):
        reagent_bottle_service.create({
            "bottle_number": bottle_number,
            "reagent_name": reagent_name,
            "cas_number": "123-45-6",
            "remaining_quantity": remaining,
            "borrowable_flag": "可借",
            "expired_flag": "正常",
        })

    def _make_course(self, course_name="测试课程", class_name="1班", students=20):
        return experiment_course_service.create({
            "semester": "2026-2027", "term": "1",
            "course_name": course_name, "class_name": class_name,
            "major": "食安", "teacher": "测试老师", "student_count": students,
        })

    def _make_item(self, course_name="测试课程", item_name="实验一"):
        return experiment_item_service.create({
            "semester": "2026-2027", "course_name": course_name,
            "seq": 1, "item_name": item_name,
        })

    # ---------------- 测试 ----------------
    def test_create_sporadic_order(self):
        """零星领用：建单 + 明细 + 扣库存 + 生成领用流水。"""
        self._make_bottle("B0001", "试剂甲", 100.0)
        self._make_bottle("B0002", "试剂乙", 50.0)

        result = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[
                {"bottle_number": "B0001", "reagent_name": "试剂甲", "remaining_quantity": 100.0},
                {"bottle_number": "B0002", "reagent_name": "试剂乙", "remaining_quantity": 50.0},
            ],
            created_by="管理员",
        )
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(result.data["item_count"], 2)

        order = borrow_order_service.get_by_id(result.data["order_id"])
        self.assertEqual(order.status, ORDER_STATUS_BORROWING)
        self.assertEqual(order.order_type, ORDER_TYPE_SPORADIC)
        self.assertIsNone(order.course_id)

        # 库存被扣减，状态置为已借出
        bottle = reagent_bottle_service.get_by_bottle_number("B0001")
        self.assertAlmostEqual(float(bottle.remaining_quantity), 0.0)
        self.assertEqual(bottle.borrowable_flag, "已借出")

        # 生成领用流水
        records = borrow_record_service.get_by_bottle_number("B0001")
        self.assertEqual(len(records), 1)
        self.assertAlmostEqual(float(records[0].borrow_quantity), 100.0)

        items = work_order_service.get_order_items(order.id)
        self.assertEqual(len(items), 2)
        self.assertAlmostEqual(items[0]["remaining_qty"], items[0]["borrow_qty"])

    def test_course_order_requires_course_and_item(self):
        """课程领用必须选择课程与实验。"""
        self._make_bottle("B0003", "试剂甲", 10.0)
        result = work_order_service.create_order(
            order_type=ORDER_TYPE_COURSE,
            applicant="张三",
            cart_items=[{"bottle_number": "B0003", "reagent_name": "试剂甲", "remaining_quantity": 10.0}],
        )
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "MISSING_COURSE_ITEM")

    def test_course_order_links_course_and_item(self):
        """课程领用：工单记录课程与实验。"""
        course = experiment_course_service.get_by_id(self._make_course())
        item = experiment_item_service.get_by_id(self._make_item())
        self._make_bottle("B0004", "试剂甲", 30.0)

        result = work_order_service.create_order(
            order_type=ORDER_TYPE_COURSE,
            applicant="李老师",
            cart_items=[{"bottle_number": "B0004", "reagent_name": "试剂甲", "remaining_quantity": 30.0}],
            course=course,
            exp_item=item,
            created_by="李老师",
        )
        self.assertTrue(result.is_success(), result.message)

        order = borrow_order_service.get_by_id(result.data["order_id"])
        self.assertEqual(order.course_id, course.id)
        self.assertEqual(order.item_id, item.id)
        self.assertEqual(order.course_name, "测试课程")
        self.assertEqual(order.item_name, "实验一")

    def test_partial_then_full_return(self):
        """严格模式（close_items=False）：部分归还 → 部分归还；补齐后 → 已归还。"""
        self._make_bottle("B0005", "试剂甲", 100.0)
        created = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[{"bottle_number": "B0005", "reagent_name": "试剂甲", "remaining_quantity": 100.0}],
        )
        order_id = created.data["order_id"]
        items = work_order_service.get_order_items(order_id)

        # 归还 40（严格模式：不结清，保持待归还）
        partial = work_order_service.return_items(
            order_id, [{"item_id": items[0]["id"], "return_qty": 40.0}], "张三",
            close_items=False,
        )
        self.assertTrue(partial.is_success(), partial.message)
        self.assertEqual(partial.data["status"], ORDER_STATUS_PARTIAL)
        self.assertAlmostEqual(
            float(reagent_bottle_service.get_by_bottle_number("B0005").remaining_quantity), 40.0
        )

        # 再归还 60 → 全部归还
        full = work_order_service.return_items(
            order_id, [{"item_id": items[0]["id"], "return_qty": 60.0}], "张三",
            close_items=False,
        )
        self.assertTrue(full.is_success(), full.message)
        self.assertEqual(full.data["status"], ORDER_STATUS_RETURNED)
        self.assertAlmostEqual(
            float(reagent_bottle_service.get_by_bottle_number("B0005").remaining_quantity), 100.0
        )

        detail = work_order_service.get_order_items(order_id)[0]
        self.assertEqual(detail["status"], "已归还")
        self.assertAlmostEqual(detail["remaining_qty"], 0.0)
        self.assertAlmostEqual(detail["returned_qty"], 100.0)

    def test_return_rejects_qty_exceeding_remaining(self):
        """归还量不得超过未归还量。"""
        self._make_bottle("B0006", "试剂甲", 50.0)
        created = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[{"bottle_number": "B0006", "reagent_name": "试剂甲", "remaining_quantity": 50.0}],
        )
        order_id = created.data["order_id"]
        items = work_order_service.get_order_items(order_id)

        result = work_order_service.return_items(
            order_id, [{"item_id": items[0]["id"], "return_qty": 80.0}], "张三"
        )
        self.assertTrue(result.is_failure())

    def test_can_return_permission(self):
        """还入权限：管理员或原领用人。"""
        self._make_bottle("B0007", "试剂甲", 10.0)
        order = borrow_order_service.get_by_id(
            work_order_service.create_order(
                order_type=ORDER_TYPE_SPORADIC,
                applicant="张三",
                cart_items=[{"bottle_number": "B0007", "reagent_name": "试剂甲", "remaining_quantity": 10.0}],
            ).data["order_id"]
        )

        self.assertTrue(work_order_service.can_return(order, "张三", is_admin=False))
        self.assertFalse(work_order_service.can_return(order, "李四", is_admin=False))
        self.assertTrue(work_order_service.can_return(order, "李四", is_admin=True))

    # ---------------- 历史工单 → 默认领用清单 ----------------
    def test_build_default_cart_from_history(self):
        """按课程+实验取最近工单，生成默认清单（沿用历史领用量、匹配当前可借瓶）。"""
        course = experiment_course_service.get_by_id(self._make_course())
        item = experiment_item_service.get_by_id(self._make_item())
        self._make_bottle("B1001", "试剂甲", 100.0)
        self._make_bottle("B1002", "试剂乙", 50.0)

        created = work_order_service.create_order(
            order_type=ORDER_TYPE_COURSE,
            applicant="李老师",
            cart_items=[
                {"bottle_number": "B1001", "reagent_name": "试剂甲", "borrow_qty": 30.0},
                {"bottle_number": "B1002", "reagent_name": "试剂乙", "borrow_qty": 10.0},
            ],
            course=course,
            exp_item=item,
            created_by="李老师",
        )
        self.assertTrue(created.is_success(), created.message)
        order_id = created.data["order_id"]

        # 全部归还，使瓶子重新可借
        items = work_order_service.get_order_items(order_id)
        work_order_service.return_items(
            order_id,
            [{"item_id": i["id"], "return_qty": i["remaining_qty"]} for i in items],
            "李老师",
        )

        result = work_order_service.build_default_cart("测试课程", "实验一")
        self.assertTrue(result.is_success(), result.message)
        cart = result.data["cart"]
        self.assertEqual(len(cart), 2)

        by_name = {entry["reagent_name"]: entry for entry in cart}
        self.assertIn("试剂甲", by_name)
        self.assertAlmostEqual(by_name["试剂甲"]["borrow_qty"], 30.0)     # 沿用历史领用量
        self.assertEqual(by_name["试剂甲"]["history_qty"], 30.0)
        self.assertEqual(by_name["试剂甲"]["bottle_number"], "B1001")     # 匹配到可借瓶

    def test_build_default_cart_without_history(self):
        """没有历史工单时应明确失败。"""
        result = work_order_service.build_default_cart("不存在的课程", "实验一")
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "NO_HISTORY_ORDER")

    def test_build_default_cart_marks_missing_stock(self):
        """历史里的试剂当前无可借库存时，应列入 missing 且不进清单。"""
        course = experiment_course_service.get_by_id(self._make_course("课程X"))
        item = experiment_item_service.get_by_id(self._make_item("课程X", "实验一"))
        self._make_bottle("B1003", "试剂丙", 20.0)

        work_order_service.create_order(
            order_type=ORDER_TYPE_COURSE,
            applicant="李老师",
            cart_items=[{"bottle_number": "B1003", "reagent_name": "试剂丙", "borrow_qty": 5.0}],
            course=course,
            exp_item=item,
        )

        # 把该瓶置为不可借（模拟库存耗尽）
        bottle = reagent_bottle_service.get_by_bottle_number("B1003")
        reagent_bottle_service.update(bottle.id, {"borrowable_flag": "耗尽"})

        result = work_order_service.build_default_cart("课程X", "实验一")
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(result.data["cart"], [])
        self.assertIn("试剂丙", result.data["missing"])

    def test_create_order_rejects_zero_quantity(self):
        """领用量为 0 时应被拒绝（不产生工单）。"""
        self._make_bottle("B1004", "试剂甲", 10.0)
        result = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[{"bottle_number": "B1004", "reagent_name": "试剂甲", "borrow_qty": 0}],
        )
        self.assertTrue(result.is_failure())

    def test_return_multiple_items_by_ratio(self):
        """多瓶工单按比例（50%）部分归还：明细已还量与工单状态正确。

        对应页面上「逐瓶百分比滑块」的归还方式。
        """
        self._make_bottle("B5001", "试剂甲", 100.0)
        self._make_bottle("B5002", "试剂乙", 200.0)

        created = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[
                {"bottle_number": "B5001", "reagent_name": "试剂甲", "borrow_qty": 20.0},
                {"bottle_number": "B5002", "reagent_name": "试剂乙", "borrow_qty": 40.0},
            ],
        )
        self.assertTrue(created.is_success(), created.message)
        order_id = created.data["order_id"]

        items = work_order_service.get_order_items(order_id)
        self.assertEqual(len(items), 2, "多瓶领用应合并为同一张工单的多条明细")

        returns = [
            {"item_id": i["id"], "return_qty": round(i["remaining_qty"] * 0.5, 4)}
            for i in items
        ]
        result = work_order_service.return_items(order_id, returns, "张三")
        self.assertTrue(result.is_success(), result.message)
        # 提交归还的明细即结清（默认 close_items=True）
        self.assertEqual(result.data["status"], ORDER_STATUS_RETURNED)

        after = {i["id"]: i for i in work_order_service.get_order_items(order_id)}
        self.assertAlmostEqual(after[items[0]["id"]]["returned_qty"], 10.0)
        self.assertAlmostEqual(after[items[1]["id"]]["returned_qty"], 20.0)
        self.assertEqual(after[items[0]["id"]]["status"], "已归还")
        self.assertEqual(after[items[1]["id"]]["status"], "已归还")

    def test_return_subset_keeps_others_pending(self):
        """借 4 瓶只还 1 瓶：该瓶结清，工单不结束，其余 3 瓶仍待归还。"""
        for idx in range(1, 5):
            self._make_bottle(f"B70{idx:02d}", "试剂甲", 100.0)

        created = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[
                {"bottle_number": f"B70{idx:02d}", "reagent_name": "试剂甲", "borrow_qty": 10.0}
                for idx in range(1, 5)
            ],
        )
        self.assertTrue(created.is_success(), created.message)
        order_id = created.data["order_id"]
        items = work_order_service.get_order_items(order_id)
        self.assertEqual(len(items), 4)

        # 只归还第 1 瓶（100%）
        result = work_order_service.return_items(
            order_id, [{"item_id": items[0]["id"], "return_qty": 10.0}], "张三"
        )
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(result.data["status"], ORDER_STATUS_PARTIAL)

        after = work_order_service.get_order_items(order_id)
        pending = [i for i in after if i["status"] != "已归还"]
        self.assertEqual(len(pending), 3, "未勾选归还的 3 瓶应保持待归还")

    def test_partial_ratio_return_closes_item(self):
        """按比例部分归还（30%）后，该明细即结清，不再出现在待还列表。"""
        self._make_bottle("B6001", "试剂甲", 100.0)
        created = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[
                {"bottle_number": "B6001", "reagent_name": "试剂甲", "borrow_qty": 20.0}
            ],
        )
        order_id = created.data["order_id"]
        item = work_order_service.get_order_items(order_id)[0]

        # 未还量 20，只还回 6（30%）
        result = work_order_service.return_items(
            order_id, [{"item_id": item["id"], "return_qty": 6.0}], "张三"
        )
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(result.data["status"], ORDER_STATUS_RETURNED)

        after = work_order_service.get_order_items(order_id)
        self.assertEqual(after[0]["status"], "已归还")
        self.assertAlmostEqual(after[0]["returned_qty"], 6.0)
        self.assertEqual(
            [i for i in after if i["status"] != "已归还"], [],
            "已结清的明细不应继续待还",
        )

    def test_strict_mode_keeps_item_pending(self):
        """close_items=False（严格模式）：未还满则保持待归还。"""
        self._make_bottle("B6002", "试剂甲", 100.0)
        created = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[
                {"bottle_number": "B6002", "reagent_name": "试剂甲", "borrow_qty": 20.0}
            ],
        )
        order_id = created.data["order_id"]
        item = work_order_service.get_order_items(order_id)[0]

        result = work_order_service.return_items(
            order_id,
            [{"item_id": item["id"], "return_qty": 6.0}],
            "张三",
            close_items=False,
        )
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(result.data["status"], ORDER_STATUS_PARTIAL)

        after = work_order_service.get_order_items(order_id)[0]
        self.assertEqual(after["status"], "待归还")
        self.assertAlmostEqual(after["remaining_qty"], 14.0)

    def test_zero_ratio_return_marks_empty_and_scrap(self):
        """归还比例 0%（空瓶）：瓶记为空瓶并进入待报废清单，明细结清。"""
        self._make_bottle("B8001", "试剂甲", 100.0)
        created = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[
                {"bottle_number": "B8001", "reagent_name": "试剂甲", "borrow_qty": 20.0}
            ],
        )
        order_id = created.data["order_id"]
        item = work_order_service.get_order_items(order_id)[0]

        result = work_order_service.return_items(
            order_id,
            [{"item_id": item["id"], "return_qty": 0.0, "discard": True}],
            "张三",
        )
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(result.data["status"], ORDER_STATUS_RETURNED)

        bottle = reagent_bottle_service.get_by_bottle_number("B8001")
        self.assertEqual(bottle.borrowable_flag, BorrowableStatus.EMPTY)
        self.assertEqual(bottle.scrap_flag, ScrapStatus.PENDING)
        self.assertAlmostEqual(float(bottle.remaining_quantity), 0.0)

        after = work_order_service.get_order_items(order_id)[0]
        self.assertEqual(after["status"], "已归还")

    def test_mixed_empty_and_pending_items(self):
        """一瓶空瓶（0%）结清、另一瓶未勾选 → 工单为「部分归还」。"""
        self._make_bottle("B8002", "试剂甲", 100.0)
        self._make_bottle("B8003", "试剂乙", 100.0)
        created = work_order_service.create_order(
            order_type=ORDER_TYPE_SPORADIC,
            applicant="张三",
            cart_items=[
                {"bottle_number": "B8002", "reagent_name": "试剂甲", "borrow_qty": 10.0},
                {"bottle_number": "B8003", "reagent_name": "试剂乙", "borrow_qty": 10.0},
            ],
        )
        order_id = created.data["order_id"]
        items = work_order_service.get_order_items(order_id)

        result = work_order_service.return_items(
            order_id,
            [{"item_id": items[0]["id"], "return_qty": 0.0, "discard": True}],
            "张三",
        )
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(result.data["status"], ORDER_STATUS_PARTIAL)

        still_pending = [
            i for i in work_order_service.get_order_items(order_id)
            if i["status"] != "已归还"
        ]
        self.assertEqual(len(still_pending), 1)
        self.assertEqual(still_pending[0]["bottle_number"], "B8003")


if __name__ == "__main__":
    unittest.main()
