"""学年：需求走一轮的时间盒子。

实验大多一年只做一次，所以「需求」这个量的自然周期不是天、不是月，而是
**学年**：每年 9 月 1 日起，到次年 9 月 1 日止，一学年的需求会在这一轮
里走完。过了 9 月 1 日就是新的一轮，上一年的单不再参与任何累计。

这个边界只解决两件事，但都是关键的两件：

1. **累计不会跨年**。同一门课一年一张单，剩下的量不会年年叠加成一座
   永远搬不动的山——两周窗口解决「最近在发生什么」，学年边界解决
   「哪些账已经翻篇」。
2. **保底有了有效范围**。「他还要用多少」只在当前学年里问，去年没结
   完的单不该继续压着今年的料。

标识沿用系统里已有的写法 ``2026-2027``（``experiment_course.semester``
与采购预估都长这样），不另起格式。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

#: 学年起点：每年 9 月 1 日。
BOUNDARY_MONTH = 9
BOUNDARY_DAY = 1


@dataclass(frozen=True, order=True)
class AcademicYear:
    """一个学年，只由起始年份确定。

    用起始年份单个字段而不是 ``(开始, 结束)`` 两个：两者是绑定关系，
    存两个就可能存出 ``2026-2028`` 这种自相矛盾的值。
    """

    start_year: int

    # ---------------------------------------------------------------- 构造
    @classmethod
    def of(cls, day: date) -> "AcademicYear":
        """某一天属于哪个学年。9 月 1 日当天算新学年。"""
        passed_boundary = (day.month, day.day) >= (BOUNDARY_MONTH, BOUNDARY_DAY)
        return cls(day.year if passed_boundary else day.year - 1)

    @classmethod
    def current(cls, today: Optional[date] = None) -> "AcademicYear":
        return cls.of(today or date.today())

    @classmethod
    def parse(cls, text: Optional[str]) -> Optional["AcademicYear"]:
        """解析 ``2026-2027``。格式不对返回 None，不猜。"""
        if not text:
            return None
        core = str(text).strip()
        head = core.split("-")[0]
        try:
            return cls(int(head))
        except (TypeError, ValueError):
            return None

    # ---------------------------------------------------------------- 边界
    @property
    def start(self) -> date:
        return date(self.start_year, BOUNDARY_MONTH, BOUNDARY_DAY)

    @property
    def end(self) -> date:
        """截止日（不含）。次年 9 月 1 日属于下一学年。"""
        return date(self.start_year + 1, BOUNDARY_MONTH, BOUNDARY_DAY)

    @property
    def label(self) -> str:
        return f"{self.start_year}-{self.start_year + 1}"

    def contains(self, day: date) -> bool:
        return self.start <= day < self.end

    def next(self) -> "AcademicYear":
        return AcademicYear(self.start_year + 1)

    def previous(self) -> "AcademicYear":
        return AcademicYear(self.start_year - 1)

    def __str__(self) -> str:
        return self.label


__all__ = ["AcademicYear", "BOUNDARY_MONTH", "BOUNDARY_DAY"]
