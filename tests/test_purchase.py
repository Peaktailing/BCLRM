"""课程采购单测试（隔离临时库，用量来自领用工单）

覆盖：
- 人均用量 = 工单用量 ÷ 课程历史人数；需求 = 人均 × 预计人数
- 同课程 + 同目标学年重复生成 → 覆盖
- 汇总时多课程共用同一试剂 → 库存只扣一次
- 管理员修改明细后标记 is_manual
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.purchase_service import purchase_service
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from services.core.borrow_order_service import (
    borrow_order_item_service,
    borrow_order_service,
)
from services.core.reagent_bottle_service import reagent_bottle_service

_TABLES = (
    "purchase_plan_item", "purchase_plan",
    "borrow_order_item", "borrow_order",
    "borrow_record", "return_record", "reagent_bottle",
    "experiment_item", "experiment_course",
)


class TestPurchaseService(unittest.TestCase):
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
    def _make_course(self, course_name, class_name="1班", students=20):
        return experiment_course_service.create({
            "semester": "2026-2027", "term": "1",
            "course_name": course_name, "class_name": class_name,
            "major": "食安", "teacher": "测试老师", "student_count": students,
        })

    def _make_item(self, course_name, item_name="实验一", seq=1):
        return experiment_item_service.create({
            "semester": "2026-2027", "course_name": course_name,
            "seq": seq, "item_name": item_name,
        })

    def _make_bottle(self, bottle_number, reagent_name, remaining):
        reagent_bottle_service.create({
            "bottle_number": bottle_number,
            "reagent_name": reagent_name,
            "cas_number": "123-45-6",
            "remaining_quantity": remaining,
            "borrowable_flag": "可借",
            "expired_flag": "正常",
        })

    def _make_order(self, order_number, reagent_name, borrow_qty, returned_qty,
                    course_id, course_name, item_id, item_name,
                    borrow_time="2025/10/15 10:00", bottle_number="B0001",
                    applicant="张三"):
        """造一张课程领用工单（用量 = 领用量 - 归还量）"""
        order_id = borrow_order_service.create({
            "order_number": order_number,
            "order_type": "课程领用",
            "applicant": applicant,
            "borrow_time": borrow_time,
            "course_id": course_id,
            "item_id": item_id,
            "course_name": course_name,
            "item_name": item_name,
            "status": "借用中",
        })
        borrow_order_item_service.create({
            "order_id": order_id,
            "bottle_number": bottle_number,
            "reagent_name": reagent_name,
            "borrow_qty": borrow_qty,
            "returned_qty": returned_qty,
            "status": "已归还" if returned_qty >= borrow_qty else "待归还",
        })
        return order_id

    # ---------------- 测试 ----------------
    def test_per_capita_usage_and_demand(self):
        """人均用量 = 用量 ÷ 历史人数；需求 = 人均 × 预计人数。"""
        course_id = self._make_course("测试课程", students=20)
        item_id = self._make_item("测试课程", "实验一 基础操作")
        # 用量 100（领 100 未归还）
        self._make_order("BO100", "试剂甲", 100.0, 0.0,
                         course_id, "测试课程", item_id, "实验一 基础操作")

        result = purchase_service.preview_course_plan("测试课程", "2025-2026", 30)
        self.assertTrue(result.is_success(), result.message)

        data = result.data
        self.assertEqual(data["source_student_count"], 20)
        self.assertEqual(len(data["items"]), 1)

        row = data["items"][0]
        self.assertEqual(row["item_name"], "实验一 基础操作")
        self.assertAlmostEqual(row["per_capita_usage"], 5.0)    # 100 / 20
        self.assertAlmostEqual(row["demand_quantity"], 150.0)   # 5 × 30

    def test_generate_and_overwrite_same_course_semester(self):
        """同课程 + 同目标学年重复生成 → 覆盖。"""
        course_id = self._make_course("测试课程", students=20)
        item_id = self._make_item("测试课程")
        self._make_order("BO101", "试剂甲", 100.0, 0.0, course_id, "测试课程", item_id, "实验一")

        first = purchase_service.generate_course_plan(
            "测试课程", "2025-2026", "2026-2027", 30, created_by="测试"
        )
        self.assertTrue(first.is_success(), first.message)
        self.assertEqual(first.data["action"], "已生成")

        second = purchase_service.generate_course_plan(
            "测试课程", "2025-2026", "2026-2027", 40, created_by="测试"
        )
        self.assertTrue(second.is_success(), second.message)
        self.assertEqual(second.data["action"], "已覆盖更新")
        self.assertEqual(second.data["plan_id"], first.data["plan_id"])

        plans = purchase_service.list_plans("2026-2027")
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].target_student_count, 40)

        detail = purchase_service.get_plan_detail(plans[0].id)
        self.assertEqual(len(detail), 1)
        self.assertAlmostEqual(detail[0]["demand_quantity"], 200.0)   # 5 × 40

    def test_summary_deducts_stock_only_once(self):
        """汇总：两门课都要试剂甲，总需求合并后库存只扣一次。"""
        course_a = self._make_course("课程A", students=20)
        course_b = self._make_course("课程B", students=10)
        item_a = self._make_item("课程A")
        item_b = self._make_item("课程B")

        self._make_bottle("B0003", "试剂甲", 100.0)
        # 课程A 用量 100（20 人 → 人均 5）→ 30 人需求 150
        self._make_order("BO102", "试剂甲", 100.0, 0.0, course_a, "课程A", item_a, "实验一")
        # 课程B 用量 20（10 人 → 人均 2）→ 30 人需求 60
        self._make_order("BO103", "试剂甲", 20.0, 0.0, course_b, "课程B", item_b, "实验一",
                         bottle_number="B0003")

        purchase_service.generate_course_plan("课程A", "2025-2026", "2026-2027", 30)
        purchase_service.generate_course_plan("课程B", "2025-2026", "2026-2027", 30)

        result = purchase_service.summarize("2026-2027")
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(len(result.data), 1)

        row = result.data[0]
        self.assertAlmostEqual(row["total_demand"], 210.0)      # 150 + 60
        self.assertAlmostEqual(row["current_stock"], 100.0)
        self.assertAlmostEqual(row["final_purchase"], 110.0)    # 210 - 100（只扣一次）
        self.assertEqual(len(row["course_detail"]), 2)

    def test_update_plan_items_marks_manual(self):
        """管理员修改明细后标记 is_manual 并同步表头总量。"""
        course_id = self._make_course("测试课程", students=20)
        item_id = self._make_item("测试课程")
        self._make_order("BO104", "试剂甲", 100.0, 0.0, course_id, "测试课程", item_id, "实验一")

        plan = purchase_service.generate_course_plan(
            "测试课程", "2025-2026", "2026-2027", 30
        ).data
        detail = purchase_service.get_plan_detail(plan["plan_id"])
        self.assertEqual(len(detail), 1)

        result = purchase_service.update_plan_items(
            plan["plan_id"],
            [{"id": detail[0]["id"], "demand_quantity": 999.0,
              "purchase_quantity": 888.0, "supplier": "某供应商", "remark": "人工调整"}],
            updated_by="管理员",
        )
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(result.data["saved"], 1)

        updated = purchase_service.get_plan_detail(plan["plan_id"])[0]
        self.assertAlmostEqual(updated["demand_quantity"], 999.0)
        self.assertAlmostEqual(updated["purchase_quantity"], 888.0)
        self.assertEqual(updated["supplier"], "某供应商")
        self.assertEqual(updated["is_manual"], 1)


if __name__ == "__main__":
    unittest.main()
