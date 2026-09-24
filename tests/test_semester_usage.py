"""学期用量统计测试（隔离临时库，基于领用工单口径）

用量 = 领用量 − 累计归还量，按「课程 + 实验 + 试剂」聚合。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.semester_stats_service import (
    semester_stats_service,
    date_to_semester,
    parse_date,
)
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from services.core.borrow_order_service import (
    borrow_order_item_service,
    borrow_order_service,
)

_TABLES = (
    "borrow_order_item", "borrow_order",
    "borrow_record", "return_record", "reagent_bottle",
    "experiment_item", "experiment_course",
)


class TestSemesterMath(unittest.TestCase):
    def test_date_to_semester(self):
        # 以每年 8 月为学年起点
        self.assertEqual(date_to_semester("2025/10/01"), "2025-2026")
        self.assertEqual(date_to_semester("2026/01/15"), "2025-2026")
        self.assertEqual(date_to_semester("2026/07/31"), "2025-2026")
        self.assertEqual(date_to_semester("2026/08/01"), "2026-2027")
        self.assertEqual(date_to_semester("2026-09-22"), "2026-2027")

    def test_invalid_date(self):
        self.assertIsNone(date_to_semester(None))
        self.assertIsNone(date_to_semester(""))
        self.assertIsNone(date_to_semester("not-a-date"))
        self.assertIsNone(parse_date("bad"))


class TestUsageCalculation(unittest.TestCase):
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

    def _make_item(self, course_name, item_name, seq=1):
        return experiment_item_service.create({
            "semester": "2026-2027", "course_name": course_name,
            "seq": seq, "item_name": item_name,
        })

    def _make_order(self, order_number, reagent_name, borrow_qty, returned_qty,
                    applicant="张三", borrow_time="2025/10/15 10:00",
                    course_id=None, course_name=None, item_id=None, item_name=None,
                    bottle_number="B0001"):
        order_id = borrow_order_service.create({
            "order_number": order_number,
            "order_type": "课程领用" if course_id else "零星领用",
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
    def test_usage_is_borrow_minus_returned(self):
        """用量 = 领用量 − 归还量。"""
        course_id = self._make_course("测试课程")
        item_id = self._make_item("测试课程", "实验一")
        # 领用 10，已归还 3 → 用量 7
        self._make_order("BO001", "试剂甲", 10.0, 3.0,
                         course_id=course_id, course_name="测试课程",
                         item_id=item_id, item_name="实验一")

        summary = semester_stats_service.get_usage_summary().data
        self.assertAlmostEqual(summary["total_usage"], 7.0)
        self.assertEqual(summary["user_count"], 1)

    def test_semester_summary_and_per_user(self):
        """按人/汇总：总量、人数、人均。"""
        course_id = self._make_course("测试课程")
        item_id = self._make_item("测试课程", "实验一")
        self._make_order("BO002", "试剂甲", 10.0, 3.0, applicant="张三",
                         course_id=course_id, course_name="测试课程",
                         item_id=item_id, item_name="实验一")
        self._make_order("BO003", "试剂乙", 20.0, 5.0, applicant="李四",
                         course_id=course_id, course_name="测试课程",
                         item_id=item_id, item_name="实验一")

        summary = semester_stats_service.get_usage_summary().data
        self.assertAlmostEqual(summary["total_usage"], 22.0)   # 7 + 15
        self.assertEqual(summary["user_count"], 2)
        self.assertAlmostEqual(summary["avg_per_user"], 11.0)

        rows = semester_stats_service.get_usage_by_user().data
        by_user = {row["领用人"]: row["用量"] for row in rows}
        self.assertAlmostEqual(by_user["张三"], 7.0)
        self.assertAlmostEqual(by_user["李四"], 15.0)
        self.assertEqual(rows[0]["领用人"], "李四")   # 倒序

    def test_usage_attributed_by_borrow_time(self):
        """用量归属按工单的领用时间。"""
        self._make_order("BO004", "试剂甲", 10.0, 5.0, borrow_time="2025/10/01 10:00")
        self._make_order("BO005", "试剂甲", 20.0, 0.0, borrow_time="2026/09/10 10:00")

        self.assertAlmostEqual(
            semester_stats_service.get_usage_summary("2025-2026").data["total_usage"], 5.0
        )
        self.assertAlmostEqual(
            semester_stats_service.get_usage_summary("2026-2027").data["total_usage"], 20.0
        )

    def test_list_semesters(self):
        self._make_order("BO006", "试剂甲", 10.0, 10.0, borrow_time="2025/11/01 10:00")
        semesters = semester_stats_service.list_semesters().data
        self.assertEqual(semesters, ["2025-2026"])

    def test_usage_by_course_with_per_capita(self):
        """按课程聚合：课程人数作分母计算人均用量。"""
        course_id = self._make_course("测试课程", students=20)
        item_id = self._make_item("测试课程", "实验一")
        self._make_order("BO007", "试剂甲", 100.0, 0.0,
                         course_id=course_id, course_name="测试课程",
                         item_id=item_id, item_name="实验一")

        rows = semester_stats_service.get_usage_by_course().data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["课程"], "测试课程")
        self.assertAlmostEqual(rows[0]["用量"], 100.0)
        self.assertEqual(rows[0]["课程人数"], 20)
        self.assertAlmostEqual(rows[0]["人均用量"], 5.0)   # 100 / 20

    def test_usage_by_reagent_with_per_capita(self):
        """按试剂统计：人均 = 该试剂用量 ÷ 领用人数（各试剂分别计算）。"""
        self._make_order("BO101", "试剂甲", 60.0, 30.0, applicant="张三")   # 用量 30
        self._make_order("BO102", "试剂乙", 30.0, 15.0, applicant="张三")   # 用量 15
        self._make_order("BO103", "试剂甲", 40.0, 10.0, applicant="李四")   # 用量 30

        rows = semester_stats_service.get_usage_by_reagent().data
        by_name = {row["试剂名称"]: row for row in rows}
        self.assertEqual(len(rows), 2)

        # 试剂甲：30 + 30 = 60，2 位领用人 → 人均 30
        self.assertAlmostEqual(by_name["试剂甲"]["用量"], 60.0)
        self.assertAlmostEqual(by_name["试剂甲"]["人均用量"], 30.0)
        self.assertEqual(by_name["试剂甲"]["领用人次"], 2)

        # 试剂乙：15，分母为全体领用人数 2 → 人均 7.5
        self.assertAlmostEqual(by_name["试剂乙"]["用量"], 15.0)
        self.assertAlmostEqual(by_name["试剂乙"]["人均用量"], 7.5)
        self.assertEqual(by_name["试剂乙"]["领用人次"], 1)

        # 与「全部加总 ÷ 人数」的笼统口径不同（那会是 75 / 2 = 37.5）
        self.assertNotAlmostEqual(by_name["试剂甲"]["人均用量"], 37.5)

        # 按用量倒序
        self.assertEqual(rows[0]["试剂名称"], "试剂甲")

        # 汇总中的试剂种类数
        self.assertEqual(
            semester_stats_service.get_usage_summary().data["reagent_count"], 2
        )

    def test_usage_by_course_item_reagent(self):
        """按「课程-实验-试剂」统计：人均 = 用量 ÷ 该课程人数。"""
        course_id = self._make_course("测试课程", students=20)
        item_id = self._make_item("测试课程", "实验一")
        item2_id = self._make_item("测试课程", "实验二", seq=2)

        # 实验一 · 试剂甲：领用 100、已还 40 → 用量 60
        self._make_order("BO201", "试剂甲", 100.0, 40.0,
                         course_id=course_id, course_name="测试课程",
                         item_id=item_id, item_name="实验一")
        # 实验二 · 试剂甲：领用 30、已还 0 → 用量 30
        self._make_order("BO202", "试剂甲", 30.0, 0.0,
                         course_id=course_id, course_name="测试课程",
                         item_id=item2_id, item_name="实验二")

        rows = semester_stats_service.get_usage_by_course_item_reagent().data
        self.assertEqual(len(rows), 2)
        by_key = {(row["实验"], row["试剂"]): row for row in rows}

        first = by_key[("实验一", "试剂甲")]
        self.assertEqual(first["课程"], "测试课程")
        self.assertEqual(first["班级数"], 1)
        self.assertEqual(first["班级平均人数"], 20)
        self.assertAlmostEqual(first["平均用量"], 60.0)
        self.assertAlmostEqual(first["人均用量"], 3.0)      # 60 / 20

        second = by_key[("实验二", "试剂甲")]
        self.assertAlmostEqual(second["平均用量"], 30.0)
        self.assertAlmostEqual(second["人均用量"], 1.5)     # 30 / 20
        self.assertEqual(second["班级平均人数"], 20)

    def test_usage_merged_across_classes_averaged(self):
        """同一课程多班级：按「实验名+试剂名」合并为一行，用量取平均（不分班级）。"""
        class1_id = self._make_course("多班课程", class_name="1班", students=20)
        class2_id = self._make_course("多班课程", class_name="2班", students=30)
        item_id = self._make_item("多班课程", "实验一")

        # 1 班用量 60，2 班用量 90
        self._make_order("BO301", "试剂甲", 60.0, 0.0,
                         course_id=class1_id, course_name="多班课程",
                         item_id=item_id, item_name="实验一")
        self._make_order("BO302", "试剂甲", 90.0, 0.0,
                         course_id=class2_id, course_name="多班课程",
                         item_id=item_id, item_name="实验一")

        rows = semester_stats_service.get_usage_by_course_item_reagent().data
        self.assertEqual(len(rows), 1, "同课程同实验同试剂应合并为一行，不按班级拆开")

        row = rows[0]
        self.assertEqual(row["班级数"], 2)
        self.assertAlmostEqual(row["合计用量"], 150.0)
        self.assertAlmostEqual(row["平均用量"], 75.0)        # 150 ÷ 2 个班
        self.assertEqual(row["班级平均人数"], 25)            # (20 + 30) ÷ 2
        self.assertAlmostEqual(row["人均用量"], 3.0)         # 75 ÷ 25（= 150 ÷ 50）


if __name__ == "__main__":
    unittest.main()
