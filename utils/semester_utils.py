"""学年 / 日期工具

供用量统计、采购预估等多个服务复用（独立于 business 层，避免循环导入）。

学年划分：以每年 **8 月** 为学年起点，标识形如 ``2025-2026``：
    - 8 月 ~ 次年 7 月 → ``(Y)-(Y+1)``
    - 1 月 ~ 7 月      → ``(Y-1)-(Y)``
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


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
    """将日期字符串换算为学年标识 ``YYYY-YYYY``（以 8 月为学年起点）"""
    dt = parse_date(date_str)
    if dt is None:
        return None
    year, month = dt.year, dt.month
    if month >= 8:
        return f"{year}-{year + 1}"
    return f"{year - 1}-{year}"


def next_semester(semester: str) -> str:
    """把 2025-2026 推成 2026-2027"""
    try:
        start, end = semester.split("-")
        return f"{int(start) + 1}-{int(end) + 1}"
    except Exception:
        return ""
