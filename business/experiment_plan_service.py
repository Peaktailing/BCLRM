"""实验默认方案业务服务

职责：
1. 维护实验的「默认方案文本」与「默认用量（人均）」
2. 支持一键「按最近一次工单导入」默认用量（人均 = 工单整班量 ÷ 当时班级人数）
3. 领用时按「人数」把默认用量折算为本次领用清单（可再单瓶调整）
4. 记录实验的领用进度（未领用 / 已借出试剂 / 已还入试剂）

用量口径：默认用量存「人均用量」，领用清单总量 = 人均用量 × 人数。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from models.base.experiment_plan import (
    SOURCE_HISTORY,
    SOURCE_MANUAL,
    STATUS_BORROWED,
    STATUS_NOT_BORROWED,
    STATUS_RETURNED,
)
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_plan_service import (
    experiment_default_usage_service,
    experiment_item_status_service,
    experiment_plan_service,
)
from services.core.borrow_order_service import (
    borrow_order_item_service,
    borrow_order_service,
)
from services.core.reagent_bottle_service import reagent_bottle_service
from utils.error_handler import logger, ServiceResult, handle_exception


class ExperimentPlanBusinessService:
    """实验默认方案与领用清单业务服务"""

    # ------------------------------------------------------------------
    # 查询 / 保存
    # ------------------------------------------------------------------
    @handle_exception(context="读取实验默认方案")
    def get_plan(self, course_name: str, item_name: str) -> ServiceResult:
        """读取实验方案文本与默认用量"""
        plan = experiment_plan_service.get_by_item(course_name, item_name)
        usages = experiment_default_usage_service.get_by_item(course_name, item_name)
        return ServiceResult.ok(data={
            "plan_text": plan.plan_text if plan else None,
            "usages": [
                {
                    "reagent_name": usage.reagent_name,
                    "qty_per_person": usage.qty_per_person,
                    "unit": usage.unit,
                    "base_qty": usage.base_qty,
                    "base_student_count": usage.base_student_count,
                    "source": usage.source,
                }
                for usage in usages
            ],
        })

    @handle_exception(context="保存实验默认方案")
    def save_plan(
        self,
        course_name: str,
        item_name: str,
        plan_text: Optional[str] = None,
        usages: Optional[List[Dict]] = None,
        replace_usages: bool = False
    ) -> ServiceResult:
        """保存实验方案文本与默认用量

        Args:
            usages: [{reagent_name, qty_per_person, unit, base_qty, base_student_count, source}, ...]
            replace_usages: True 时整体覆盖（先清空该实验的默认用量）
        """
        if not course_name or not item_name:
            return ServiceResult.fail(message="缺少课程或实验名称", error_code="MISSING_KEY")

        if not experiment_plan_service.upsert(course_name, item_name, plan_text):
            return ServiceResult.fail(message="保存实验方案失败", error_code="SAVE_PLAN_FAILED")

        saved = 0
        if usages is not None:
            if replace_usages:
                experiment_default_usage_service.delete_by_item(course_name, item_name)
            for usage in usages:
                reagent_name = str(usage.get("reagent_name") or "").strip()
                if not reagent_name:
                    continue
                ok = experiment_default_usage_service.upsert({
                    "course_name": course_name,
                    "item_name": item_name,
                    "reagent_name": reagent_name,
                    "qty_per_person": usage.get("qty_per_person"),
                    "unit": usage.get("unit"),
                    "base_qty": usage.get("base_qty"),
                    "base_student_count": usage.get("base_student_count"),
                    "source": usage.get("source") or SOURCE_MANUAL,
                })
                saved += 1 if ok else 0

        logger.info(
            "实验默认方案保存完成",
            course_name=course_name, item_name=item_name, usage_count=saved
        )
        return ServiceResult.ok(
            data={"usage_count": saved},
            message="实验方案与默认用量已保存"
        )

    # ------------------------------------------------------------------
    # 按最近一次工单导入默认用量
    # ------------------------------------------------------------------
    @handle_exception(context="按历史工单导入默认用量")
    def import_usage_from_history(
        self,
        course_name: str,
        item_name: str,
        student_count: Optional[int] = None
    ) -> ServiceResult:
        """把最近一次课程领用工单的明细折算为「人均用量」写入默认用量"""
        orders = [
            order for order in borrow_order_service.get_all_parsed()
            if order.course_name == course_name and order.item_name == item_name
        ]
        if not orders:
            return ServiceResult.fail(
                message="该实验没有历史工单，无法导入默认用量",
                error_code="NO_HISTORY_ORDER"
            )
        orders.sort(key=lambda o: getattr(o, "borrow_time", "") or "", reverse=True)
        latest = orders[0]

        items = borrow_order_item_service.get_by_order(latest.id)
        if not items:
            return ServiceResult.fail(message="历史工单没有明细", error_code="EMPTY_HISTORY")

        # 人数：显式传入 > 工单关联课程班级人数 > 取不到则按原量记为默认量
        base_count = student_count
        if not base_count and latest.course_id:
            course = experiment_course_service.get_by_id(latest.course_id)
            base_count = getattr(course, "student_count", None) if course else None
        base_count = int(base_count) if base_count else None

        imported = 0
        for item in items:
            qty = float(item.borrow_qty or 0)
            per_person = round(qty / base_count, 4) if base_count else qty
            if experiment_default_usage_service.upsert({
                "course_name": course_name,
                "item_name": item_name,
                "reagent_name": item.reagent_name,
                "qty_per_person": per_person,
                "base_qty": qty,
                "base_student_count": base_count,
                "source": SOURCE_HISTORY,
            }):
                imported += 1

        note = (
            f"（按 {base_count} 人折算人均）" if base_count
            else "（未取到班级人数，按原量作为人均）"
        )
        logger.info(
            "按历史工单导入默认用量完成",
            course_name=course_name, item_name=item_name,
            order_number=latest.order_number, imported=imported, base_count=base_count
        )
        return ServiceResult.ok(
            data={
                "imported": imported,
                "order_number": latest.order_number,
                "base_student_count": base_count,
            },
            message=f"已按工单 {latest.order_number} 导入 {imported} 条默认用量{note}"
        )

    # ------------------------------------------------------------------
    # 按人数生成领用清单
    # ------------------------------------------------------------------
    def _available_bottles(self) -> Dict[str, List]:
        """当前可借试剂瓶索引：试剂名 -> [瓶...]"""
        index: Dict[str, List] = defaultdict(list)
        for bottle in reagent_bottle_service.get_all_parsed():
            name = getattr(bottle, "reagent_name", None)
            if not name:
                continue
            if getattr(bottle, "borrowable_flag", None) != "可借":
                continue
            if float(getattr(bottle, "remaining_quantity", 0) or 0) <= 0:
                continue
            index[name].append(bottle)
        return index

    @handle_exception(context="按默认方案生成领用清单")
    def build_cart(
        self,
        course_name: str,
        item_name: str,
        student_count: Optional[int] = None
    ) -> ServiceResult:
        """按默认方案 + 人数生成领用清单（总量 = 人均用量 × 人数）"""
        usages = experiment_default_usage_service.get_by_item(course_name, item_name)
        if not usages:
            return ServiceResult.fail(
                message="该实验还没有默认用量方案",
                error_code="NO_DEFAULT_USAGE"
            )

        count = int(student_count) if student_count else 1
        available = self._available_bottles()

        cart: List[Dict] = []
        missing: List[str] = []
        for usage in usages:
            name = usage.reagent_name
            per_person = float(usage.qty_per_person or 0)
            total = round(per_person * count, 4)
            pool = available.get(name) or []
            if not pool:
                missing.append(name)
                continue
            bottle = pool.pop(0)
            cart.append({
                "bottle_number": getattr(bottle, "bottle_number", None),
                "reagent_name": getattr(bottle, "reagent_name", None) or name,
                "cas_number": getattr(bottle, "cas_number", None),
                "specification": getattr(bottle, "specification", None),
                "remaining_quantity": getattr(bottle, "remaining_quantity", None),
                "borrow_qty": total,
                "qty_per_person": per_person,
                "student_count": count,
            })

        message = f"已按默认方案（{count} 人）生成 {len(cart)} 条领用清单"
        if missing:
            message += f"；{len(missing)} 种试剂当前无可借库存：{'、'.join(missing)}"

        logger.info(
            "按默认方案生成领用清单",
            course_name=course_name, item_name=item_name,
            student_count=count, cart_count=len(cart), missing_count=len(missing)
        )
        return ServiceResult.ok(
            data={"cart": cart, "missing": missing, "student_count": count},
            message=message
        )

    # ------------------------------------------------------------------
    # 实验进度状态
    # ------------------------------------------------------------------
    def mark_borrowed(self, semester, course_name, item_name, borrow_time=None) -> bool:
        """标记实验为「已借出试剂」"""
        return experiment_item_status_service.set_status(
            semester, course_name, item_name, STATUS_BORROWED, borrow_time=borrow_time
        )

    def mark_returned(self, semester, course_name, item_name, return_time=None) -> bool:
        """标记实验为「已还入试剂」"""
        return experiment_item_status_service.set_status(
            semester, course_name, item_name, STATUS_RETURNED, return_time=return_time
        )

    def get_status_map(self, semester: Optional[str] = None) -> Dict[tuple, str]:
        """{(课程名, 实验名): 状态}"""
        return {
            (row.course_name, row.item_name): row.status or STATUS_NOT_BORROWED
            for row in experiment_item_status_service.get_by_semester(semester)
        }


# 全局实例
experiment_plan_business = ExperimentPlanBusinessService()
