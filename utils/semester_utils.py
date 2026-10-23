"""学年 / 日期工具

供用量统计、采购预估等多个服务复用（独立于 business 层，避免循环导入）。

学年划分以 **9 月 1 日** 为起点，标识形如 ``2025-2026``：
    - 9 月 ~ 次年 8 月 → ``(Y)-(Y+1)``
    - 1 月 ~ 8 月      → ``(Y-1)-(Y)``

边界规则只有一处实现：:class:`domain.academic_year.AcademicYear`。本模块
只是给老调用点留的薄壳，避免为了统一口径去改十几个调用方。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from domain.academic_year import AcademicYear


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """解析归一化日期字符串（支持 YYYY/MM/DD、YYYY-MM-DD、YYYY.MM.DD）"""
    if not date_str:
        return None
    cleaned = str(date_str).strip()[:10].replace('-', '/').replace('.', '/')
    try:
        return datetime.strptime(cleaned, "%Y/%m/%d")
    except ValueError:
        return None


def date_to_semester(date_str: Optional[str]) -> Optional[str]:
    """将日期字符串换算为学年标识 ``YYYY-YYYY``（以 9 月 1 日为学年起点）"""
    dt = parse_date(date_str)
    if dt is None:
        return None
    return AcademicYear.of(dt.date()).label


def current_semester(today: Optional[date] = None) -> str:
    """今天属于哪个学年。"""
    return AcademicYear.current(today).label


def semester_range(semester: Optional[str]) -> Optional[tuple[date, date]]:
    """学年的 ``(起, 止)`` 日期，止日不含。解析不了返回 None。"""
    year = AcademicYear.parse(semester)
    if year is None:
        return None
    return year.start, year.end


def next_semester(semester: str) -> str:
    """把 2025-2026 推成 2026-2027"""
    year = AcademicYear.parse(semester)
    return year.next().label if year else ""
