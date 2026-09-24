"""实验默认方案 / 默认用量 / 实验进度状态 测试（隔离临时库）

覆盖：
- 方案文本与默认用量（人均）的保存与读取
- 按「人数」把默认用量折算为本次领用清单
- 按最近一次工单导入默认用量（整班量 → 人均）
- 实验进度状态：领用后「已借出试剂」、全部归还后「已还入试剂」
- 分组表导入时实验项目跨学年去重
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.course_import_service import course_import_service
from business.experiment_plan_service import experiment_plan_business
from business.work_order_service import work_order_service
from models.core.borrow_order import ORDER_TYPE_COURSE
from models.base.experiment_plan import (
    STATUS_BORROWED,
    STATUS_NOT_BORROWED,
    STATUS_RETURNED,
)
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from services.core.reagent_bottle_service import reagent_bottle_service

_TABLES = (
    "borrow_order_item", "borrow_order",
    "borrow_record", "return_record", "reagent_bottle",
    "experiment_item", "experiment_course",
    "experiment_plan", "experiment_default_usage", "experiment_item_status",
)


class TestExperimentPlan(unittest.TestCase):
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

    def _make_course(self, course_name="测试课程", class_name="1班", students=30):
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

    # ---------------- 方案与默认用量 ----------------
    def test_save_and_get_plan(self):
        """方案文本与默认用量可保存并被读取。"""
        result = experiment_plan_business.save_plan(
            "测试课程", "实验一",
            plan_text="实验目的：配制培养基",
            usages=[
                {"reagent_name": "试剂甲", "qty_per_person": 2.0, "unit": "g"},
                {"reagent_name": "试剂乙", "qty_per_person": 0.5, "unit": "mL"},
            ],
            replace_usages=True,
        )
        self.assertTrue(result.is_success(), result.message)

        plan = experiment_plan_business.get_plan("测试课程", "实验一").data
        self.assertEqual(plan["plan_text"], "实验目的：配制培养基")
        self.assertEqual(len(plan["usages"]), 2)
        by_name = {u["reagent_name"]: u for u in plan["usages"]}
        self.assertAlmostEqual(by_name["试剂甲"]["qty_per_person"], 2.0)

    def test_build_cart_by_student_count(self):
        """按默认用量 × 人数生成领用清单。"""
        self._make_bottle("B2001", "试剂甲", 200.0)
        experiment_plan_business.save_plan(
            "测试课程", "实验一",
            usages=[{"reagent_name": "试剂甲", "qty_per_person": 2.0, "unit": "g"}],
            replace_usages=True,
        )

        result = experiment_plan_business.build_cart("测试课程", "实验一", student_count=30)
        self.assertTrue(result.is_success(), result.message)
        cart = result.data["cart"]
        self.assertEqual(len(cart), 1)
        self.assertAlmostEqual(cart[0]["borrow_qty"], 60.0)      # 2.0 × 30
        self.assertAlmostEqual(cart[0]["qty_per_person"], 2.0)
        self.assertEqual(cart[0]["bottle_number"], "B2001")

    def test_build_cart_without_plan(self):
        """没有默认方案时应明确失败。"""
        result = experiment_plan_business.build_cart("测试课程", "实验一", student_count=30)
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "NO_DEFAULT_USAGE")

    # ---------------- 从历史工单导入 ----------------
    def test_import_usage_from_history(self):
        """整班领用量按班级人数折算为人均用量。"""
        course_id = self._make_course(students=30)
        course = experiment_course_service.get_by_id(course_id)
        item_id = self._make_item()
        item = experiment_item_service.get_by_id(item_id)
        self._make_bottle("B3001", "试剂甲", 500.0)

        created = work_order_service.create_order(
            order_type=ORDER_TYPE_COURSE,
            applicant="李老师",
            cart_items=[
                {"bottle_number": "B3001", "reagent_name": "试剂甲", "borrow_qty": 60.0}
            ],
            course=course,
            exp_item=item,
        )
        self.assertTrue(created.is_success(), created.message)

        result = experiment_plan_business.import_usage_from_history("测试课程", "实验一")
        self.assertTrue(result.is_success(), result.message)
        self.assertEqual(result.data["base_student_count"], 30)

        plan = experiment_plan_business.get_plan("测试课程", "实验一").data
        usage = plan["usages"][0]
        self.assertAlmostEqual(usage["qty_per_person"], 2.0)      # 60 / 30
        self.assertAlmostEqual(usage["base_qty"], 60.0)
        self.assertEqual(usage["source"], "历史工单")

    def test_import_usage_without_history(self):
        """没有历史工单时导入应失败。"""
        result = experiment_plan_business.import_usage_from_history("测试课程", "实验一")
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "NO_HISTORY_ORDER")

    # ---------------- 实验进度状态 ----------------
    def test_status_marked_on_borrow_and_return(self):
        """领用后标记「已借出试剂」，全部归还后标记「已还入试剂」。"""
        course_id = self._make_course()
        course = experiment_course_service.get_by_id(course_id)
        item_id = self._make_item()
        item = experiment_item_service.get_by_id(item_id)
        self._make_bottle("B4001", "试剂甲", 100.0)

        # 初始：未领用
        status_map = experiment_plan_business.get_status_map()
        self.assertEqual(
            status_map.get(("测试课程", "实验一"), STATUS_NOT_BORROWED),
            STATUS_NOT_BORROWED,
        )

        created = work_order_service.create_order(
            order_type=ORDER_TYPE_COURSE,
            applicant="李老师",
            cart_items=[
                {"bottle_number": "B4001", "reagent_name": "试剂甲", "borrow_qty": 20.0}
            ],
            course=course,
            exp_item=item,
        )
        self.assertTrue(created.is_success(), created.message)
        self.assertEqual(
            experiment_plan_business.get_status_map()[("测试课程", "实验一")],
            STATUS_BORROWED,
        )

        # 全部归还
        order_id = created.data["order_id"]
        items = work_order_service.get_order_items(order_id)
        work_order_service.return_items(
            order_id,
            [{"item_id": i["id"], "return_qty": i["remaining_qty"]} for i in items],
            "李老师",
        )
        self.assertEqual(
            experiment_plan_business.get_status_map()[("测试课程", "实验一")],
            STATUS_RETURNED,
        )

    # ---------------- 导入去重 ----------------
    def test_import_dedups_items_across_semesters(self):
        """同一「课程名 + 实验名」跨学年只保留一条实验项目。"""
        courses = [{
            "course_name": "课程A", "class_name": "1班",
            "major": "食安", "teacher": "张老师", "student_count": 30,
        }]
        items = [{"course_name": "课程A", "item_name": "实验一", "seq": 1}]

        first = course_import_service.import_courses(
            courses, semester="2026-2027", term="1", items=items
        )
        self.assertTrue(first.is_success(), first.message)
        self.assertEqual(first.data["item_created"], 1)

        # 新学年再次导入同样的实验项目 → 不新增，只更新（去重）
        second = course_import_service.import_courses(
            courses, semester="2027-2028", term="1", items=items
        )
        self.assertTrue(second.is_success(), second.message)
        self.assertEqual(second.data["item_created"], 0)
        self.assertEqual(second.data["item_updated"], 1)

        matched = [
            i for i in experiment_item_service.get_all_parsed()
            if i.item_name == "实验一"
        ]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].semester, "2027-2028")   # 学年刷新为最新

        # 按课程查询也应去重（只返回一条）
        self.assertEqual(len(experiment_item_service.get_by_course("课程A")), 1)

    def test_delete_item_keeps_course_and_others(self):
        """删除实验项目：课程与其他实验项目保留。"""
        courses = [{
            "course_name": "课程B", "class_name": "1班",
            "major": "食安", "teacher": "张老师", "student_count": 30,
        }]
        items = [
            {"course_name": "课程B", "item_name": "实验一", "seq": 1},
            {"course_name": "课程B", "item_name": "实验二", "seq": 2},
        ]
        result = course_import_service.import_courses(
            courses, semester="2026-2027", term="1", items=items
        )
        self.assertTrue(result.is_success(), result.message)

        target = next(
            i for i in experiment_item_service.get_by_course("课程B")
            if i.item_name == "实验一"
        )
        self.assertTrue(experiment_item_service.delete(target.id))

        # 课程保留
        remain_courses = experiment_course_service.get_by_semester("2026-2027")
        self.assertEqual(len(remain_courses), 1)
        self.assertEqual(remain_courses[0].course_name, "课程B")

        # 其他实验项目保留
        remain_items = [
            i.item_name for i in experiment_item_service.get_by_course("课程B")
        ]
        self.assertEqual(remain_items, ["实验二"])

    def test_create_course_and_item_manually(self):
        """手动新增课程与实验项目（对应超管录入入口）。"""
        course_id = experiment_course_service.create({
            "semester": "2026-2027", "term": "1",
            "course_name": "手动课程", "class_name": "1班",
            "teacher": "王老师", "student_count": 25,
        })
        self.assertTrue(course_id)

        found = [
            c for c in experiment_course_service.get_by_semester("2026-2027")
            if c.course_name == "手动课程"
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].student_count, 25)

        item_id = experiment_item_service.create({
            "semester": "2026-2027", "course_name": "手动课程",
            "seq": 1, "item_name": "实验一",
        })
        self.assertTrue(item_id)
        self.assertEqual(
            [i.item_name for i in experiment_item_service.get_by_course("手动课程")],
            ["实验一"],
        )


if __name__ == "__main__":
    unittest.main()
