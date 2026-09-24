"""课程导入测试（隔离临时库）

覆盖：班级名规范化、标题解析、分组表解析、幂等导入。
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB
from business.course_import_service import (
    course_import_service,
    normalize_class_name,
    parse_title,
)
from services.base.experiment_course_service import experiment_course_service

_TABLES = ("experiment_course",)


def _make_csv() -> str:
    """构造与学院模板同构的最小 CSV（30 列，地点在第 28 列）"""
    def row(values):
        cells = [""] * 30
        for idx, val in values.items():
            cells[idx] = val
        return ",".join(cells)

    return "\n".join([
        row({0: "测试学院2026-2027-1实验项目分组表"}),
        row({0: "序号", 1: "教师", 2: "课程名称", 3: "开课专业", 4: "开课班级",
             5: "班级人数", 6: "实验项目", 7: "第一组"}),
        row({7: "周次", 8: "星期", 9: "日期", 10: "节次", 11: "人数"}),
        row({1: "王老师", 2: "测试实验课", 3: "食安", 4: "24级1班",
             5: "20", 6: "实验一", 27: "E101"}),
        row({1: "李老师", 2: "测试实验课", 3: "食安", 4: "24级1班",
             5: "20", 6: "实验二", 27: "E101"}),
    ])


class TestParseHelpers(unittest.TestCase):
    def test_normalize_class_name(self):
        self.assertEqual(normalize_class_name("24级1班"), "2024级1班")
        self.assertEqual(normalize_class_name("25级2班"), "2025级2班")
        self.assertEqual(normalize_class_name("2024级1班"), "2024级1班")
        self.assertEqual(
            normalize_class_name("2026级食品质量与安全1,2班"),
            "2026级食品质量与安全1,2班",
        )
        self.assertIsNone(normalize_class_name(None))

    def test_parse_title(self):
        college, semester, term = parse_title("生物与食品工程学院2026-2027-1实验项目分组表")
        self.assertEqual(college, "生物与食品工程学院")
        self.assertEqual(semester, "2026-2027")
        self.assertEqual(term, "1")
        self.assertEqual(parse_title("无效标题"), (None, None, None))


class TestCourseImport(unittest.TestCase):
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

    def test_parse(self):
        parsed = course_import_service.parse(io.StringIO(_make_csv()), "test.csv")
        self.assertTrue(parsed.is_success(), parsed.message)

        info = parsed.data
        self.assertEqual(info["semester"], "2026-2027")
        self.assertEqual(info["term"], "1")
        self.assertEqual(info["college"], "测试学院")
        self.assertEqual(len(info["courses"]), 1)

        course = info["courses"][0]
        self.assertEqual(course["course_name"], "测试实验课")
        self.assertEqual(course["class_name"], "2024级1班")   # 已规范化
        self.assertEqual(course["student_count"], 20)
        self.assertEqual(course["location"], "E101")
        self.assertEqual(course["teacher"], "王老师、李老师")   # 教师合并

    def test_import_is_idempotent(self):
        parsed = course_import_service.parse(io.StringIO(_make_csv()), "test.csv").data
        courses = parsed["courses"]

        first = course_import_service.import_courses(
            courses, parsed["semester"], parsed["term"], parsed["college"]
        )
        self.assertTrue(first.is_success(), first.message)
        self.assertEqual(first.data["inserted"], 1)
        self.assertEqual(first.data["updated"], 0)

        second = course_import_service.import_courses(
            courses, parsed["semester"], parsed["term"], parsed["college"]
        )
        self.assertEqual(second.data["inserted"], 0)
        self.assertEqual(second.data["updated"], 1)

        rows = experiment_course_service.get_by_semester("2026-2027")
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
