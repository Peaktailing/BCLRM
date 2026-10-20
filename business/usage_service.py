"""用量汇总服务（统一口径，基于领用工单）

用量口径：
    用量 = 领用量 − 累计归还量
按「课程 + 实验 + 试剂」聚合，数据源为领用工单（borrow_order + borrow_order_item）。

学期归属：按工单的 `borrow_time`（领用时间）。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from services.core.borrow_order_service import (
    borrow_order_item_service,
    borrow_order_service,
)
from models.core.borrow_order import (
    ORDER_STATUS_BORROWING,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_RETURNED,
)
from utils.error_handler import logger
from utils.semester_utils import date_to_semester

# 只有「已生效」的工单才计入用量：待审批（尚未执行领用）与已驳回（永不会归还）
# 的工单若计入，会让「用量 = 领用量 − 归还量」永久偏大，并污染采购人均用量测算。
USAGE_ORDER_STATUSES = (
    ORDER_STATUS_BORROWING,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_RETURNED,
)


def is_effective_order(order) -> bool:
    """判断工单是否已生效（可计入用量统计）"""
    return (getattr(order, "status", None) or "") in USAGE_ORDER_STATUSES


class UsageService:
    """用量汇总服务"""

    def collect(
        self,
        semester: Optional[str] = None,
        course_name: Optional[str] = None,
        only_course: bool = False
    ) -> List[Dict]:
        """汇总用量明细

        Args:
            semester: 学年筛选（按领用时间），None 表示全部
            course_name: 课程名筛选
            only_course: 只统计关联了课程的工单（零星领用会被排除）

        Returns:
            [{course_id, course_name, item_id, item_name, reagent_name,
              usage, order_count, applicants}]
        """
        orders = borrow_order_service.get_all_parsed()
        items_cache: Dict[int, list] = {}
        aggregated: Dict[tuple, Dict] = {}

        for order in orders:
            # 仅统计实际执行过领用的工单（借用中/部分归还/已归还）：
            # 待审批/已驳回/已撤回从未扣库存，计入会虚增用量与采购人均测算
            if not is_effective_order(order):
                continue
            if only_course and not order.course_id:
                continue
            if course_name and order.course_name != course_name:
                continue
            if semester and date_to_semester(getattr(order, "borrow_time", None)) != semester:
                continue

            order_items = items_cache.get(order.id)
            if order_items is None:
                order_items = borrow_order_item_service.get_by_order(order.id)
                items_cache[order.id] = order_items

            for item in order_items:
                usage = float(item.borrow_qty or 0) - float(item.returned_qty or 0)
                if usage <= 0:
                    continue
                key = (
                    order.course_id, order.course_name,
                    order.item_id, order.item_name,
                    item.reagent_name, getattr(item, "unit", None) or "g",
                )
                row = aggregated.setdefault(key, {
                    "usage": 0.0,
                    "order_numbers": set(),
                    "applicants": set(),
                })
                row["usage"] += usage
                row["order_numbers"].add(order.order_number)
                row["applicants"].add(order.applicant)

        results: List[Dict] = []
        for (
            course_id, course_name_value, item_id, item_name,
            reagent_name, unit,
        ), row in aggregated.items():
            results.append({
                "course_id": course_id,
                "course_name": course_name_value,
                "item_id": item_id,
                "item_name": item_name,
                "reagent_name": reagent_name,
                "unit": unit,
                "usage": round(row["usage"], 2),
                "order_count": len(row["order_numbers"]),
                "applicants": sorted(row["applicants"]),
            })
        return results

    def total_usage(self, semester: Optional[str] = None) -> float:
        """全部用量合计"""
        return round(sum(row["usage"] for row in self.collect(semester)), 2)

    def usage_by_user(self, semester: Optional[str] = None) -> List[Dict]:
        """按领用人聚合用量（一次工单可能多人，按领用人去重计数）"""
        orders = borrow_order_service.get_all_parsed()
        items_cache: Dict[int, list] = {}
        by_user: Dict[tuple, float] = defaultdict(float)
        orders_by_user: Dict[tuple, set] = defaultdict(set)

        for order in orders:
            if not is_effective_order(order):
                continue
            if semester and date_to_semester(getattr(order, "borrow_time", None)) != semester:
                continue
            order_items = items_cache.get(order.id)
            if order_items is None:
                order_items = borrow_order_item_service.get_by_order(order.id)
                items_cache[order.id] = order_items
            for item in order_items:
                usage = max(
                    0.0,
                    float(item.borrow_qty or 0) - float(item.returned_qty or 0),
                )
                if usage <= 0:
                    continue
                unit = getattr(item, "unit", None) or "g"
                key = (order.applicant, unit)
                by_user[key] += usage
                orders_by_user[key].add(order.order_number)

        total = sum(by_user.values())
        rows = [
            {
                "领用人": user,
                "单位": unit,
                "用量": round(usage, 2),
                "工单数": len(orders_by_user[(user, unit)]),
                "占比": f"{(usage / total * 100):.1f}%" if total else "0.0%",
            }
            for (user, unit), usage in by_user.items()
        ]
        rows.sort(key=lambda item: item["用量"], reverse=True)
        return rows

    def usage_by_month(self, semester: Optional[str] = None) -> Dict[str, float]:
        """按月份聚合用量（跟随领用时间）"""
        from utils.semester_utils import parse_date

        orders = borrow_order_service.get_all_parsed()
        items_cache: Dict[int, list] = {}
        by_month: Dict[str, float] = defaultdict(float)

        for order in orders:
            # 与 collect() 口径一致：排除待审批/已驳回/已撤回等未生效工单
            if not is_effective_order(order):
                continue
            if semester and date_to_semester(getattr(order, "borrow_time", None)) != semester:
                continue
            dt = parse_date(getattr(order, "borrow_time", None))
            if dt is None:
                continue
            order_items = items_cache.get(order.id)
            if order_items is None:
                order_items = borrow_order_item_service.get_by_order(order.id)
                items_cache[order.id] = order_items
            usage = sum(
                max(0.0, float(i.borrow_qty or 0) - float(i.returned_qty or 0))
                for i in order_items
            )
            if usage > 0:
                by_month[f"{dt.year:04d}-{dt.month:02d}"] += usage

        return {month: round(value, 2) for month, value in sorted(by_month.items())}

    def list_semesters(self) -> List[str]:
        """存在工单的学年（倒序）"""
        semesters = {
            date_to_semester(getattr(order, "borrow_time", None))
            for order in borrow_order_service.get_all_parsed()
            if is_effective_order(order)
        }
        return sorted({s for s in semesters if s}, reverse=True)


# 全局实例
usage_service = UsageService()
logger.debug("用量汇总服务初始化完成")
