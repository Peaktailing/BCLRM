"""学年：一年一轮的时间盒子，边界是 9 月 1 日。"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.academic_year import AcademicYear
from utils.semester_utils import (
    current_semester,
    date_to_semester,
    next_semester,
    semester_range,
)


class TestBoundary(unittest.TestCase):
    """9 月 1 日当天算新学年，8 月 31 日还算旧的。"""

    def test_day_before_boundary_stays_in_old_year(self):
        self.assertEqual(AcademicYear.of(date(2026, 8, 31)).label, "2025-2026")

    def test_boundary_day_starts_new_year(self):
        self.assertEqual(AcademicYear.of(date(2026, 9, 1)).label, "2026-2027")

    def test_year_rolls_over_in_january(self):
        self.assertEqual(AcademicYear.of(date(2027, 1, 15)).label, "2026-2027")

    def test_summer_belongs_to_the_year_that_just_ended(self):
        """7、8 月是上一学年的尾巴，不是新学年的开头。"""
        self.assertEqual(AcademicYear.of(date(2027, 7, 1)).label, "2026-2027")


class TestRange(unittest.TestCase):
    def test_start_and_end(self):
        year = AcademicYear(2026)
        self.assertEqual(year.start, date(2026, 9, 1))
        self.assertEqual(year.end, date(2027, 9, 1))

    def test_end_is_exclusive(self):
        year = AcademicYear(2026)
        self.assertTrue(year.contains(date(2027, 8, 31)))
        self.assertFalse(year.contains(date(2027, 9, 1)))

    def test_next_and_previous(self):
        year = AcademicYear(2026)
        self.assertEqual(year.next().label, "2027-2028")
        self.assertEqual(year.previous().label, "2025-2026")

    def test_ordering(self):
        self.assertLess(AcademicYear(2025), AcademicYear(2026))


class TestLabel(unittest.TestCase):
    def test_parse_roundtrip(self):
        self.assertEqual(AcademicYear.parse("2026-2027"), AcademicYear(2026))
        self.assertEqual(AcademicYear.parse("2026-2027").label, "2026-2027")

    def test_parse_rejects_garbage(self):
        self.assertIsNone(AcademicYear.parse(None))
        self.assertIsNone(AcademicYear.parse(""))
        self.assertIsNone(AcademicYear.parse("not-a-year"))

    def test_current_uses_today(self):
        self.assertEqual(AcademicYear.current(date(2026, 10, 23)).label, "2026-2027")


class TestSemesterUtils(unittest.TestCase):
    """老调用点的接口不变，边界统一到 9/1。"""

    def test_date_to_semester(self):
        self.assertEqual(date_to_semester("2026/08/31"), "2025-2026")
        self.assertEqual(date_to_semester("2026/09/01"), "2026-2027")

    def test_current_semester(self):
        self.assertEqual(current_semester(date(2026, 10, 23)), "2026-2027")

    def test_semester_range(self):
        self.assertEqual(
            semester_range("2026-2027"), (date(2026, 9, 1), date(2027, 9, 1))
        )
        self.assertIsNone(semester_range("乱写的"))

    def test_next_semester(self):
        self.assertEqual(next_semester("2026-2027"), "2027-2028")
        self.assertEqual(next_semester("乱写的"), "")


if __name__ == "__main__":
    unittest.main()
