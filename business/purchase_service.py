"""课程采购单业务服务

核心口径：
    1. 按「课程名 + 实验 + 试剂」汇总来源学年用量
    2. 人均用量 = 该课程该实验该试剂的历史总用量 ÷ 该课程历史总人数
    3. 需求量   = 人均用量 × 预计人数（默认 30）
    4. 同一课程（课程名 + 目标学年）重复生成时**覆盖**旧单
    5. 课程采购单**不扣库存**（库存仅作参考）；
       只有超管「汇总」时才按试剂合并所有课程需求，统一扣减一次库存
       —— 避免多门课共用同一试剂时把库存重复扣减
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from business.usage_service import usage_service
from utils.semester_utils import date_to_semester
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from services.core.borrow_record_service import borrow_record_service
from services.core.purchase_plan_service import (
    purchase_plan_item_service,
    purchase_plan_service,
)
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.return_record_service import return_record_service
from utils.error_handler import logger, ServiceResult, handle_exception

DEFAULT_TARGET_STUDENT_COUNT = 30


class PurchaseService:
    """课程采购单业务服务"""

    # ------------------------------------------------------------------
    # 基础数据
    # ------------------------------------------------------------------
    def list_course_names(self, semester: Optional[str] = None) -> List[str]:
        """可选择的课程名列表（去重排序）"""
        names = {
            course.course_name
            for course in experiment_course_service.get_by_semester(semester)
            if course.course_name
        }
        return sorted(names)

    def _stock_by_reagent(self) -> Dict[str, float]:
        """当前库存：按试剂名汇总（所有试剂瓶剩余量）"""
        stock: Dict[str, float] = defaultdict(float)
        for bottle in reagent_bottle_service.get_all_parsed():
            name = getattr(bottle, "reagent_name", None)
            if name:
                stock[name] += float(getattr(bottle, "remaining_quantity", 0) or 0)
        return stock

    def _bottle_meta(self) -> Dict[str, Dict]:
        """试剂 -> (CAS / 供应商 / 单价) 参考信息"""
        meta: Dict[str, Dict] = {}
        for bottle in reagent_bottle_service.get_all_parsed():
            name = getattr(bottle, "reagent_name", None)
            if name and name not in meta:
                meta[name] = {
                    "cas_number": getattr(bottle, "cas_number", None),
                    "supplier": getattr(bottle, "supplier", None),
                    "unit_price": getattr(bottle, "unit_price", None),
                }
        return meta

    # ------------------------------------------------------------------
    # 人均用量 → 需求计算（不落库）
    # ------------------------------------------------------------------
    def calculate_course_demand(
        self,
        course_name: str,
        source_semester: str,
        target_student_count: int = DEFAULT_TARGET_STUDENT_COUNT
    ) -> Tuple[int, List[Dict]]:
        """计算某课程（课程名）按人均用量预估的需求明细

        Returns:
            (历史人数, 明细列表)
        """
        # 课程按「课程名」匹配，不限学年：分组表通常只有当前学年，
        # 而历史用量可能来自上一学年
        courses = [
            c for c in experiment_course_service.get_by_semester(None)
            if c.course_name == course_name
        ]
        if not courses:
            return 0, []

        source_students = sum(int(c.student_count or 0) for c in courses)

        # 用量：基于领用工单（用量 = 领用量 − 累计归还量）
        usage_rows = usage_service.collect(
            semester=source_semester, course_name=course_name, only_course=True
        )

        stock = self._stock_by_reagent()
        meta = self._bottle_meta()

        rows: List[Dict] = []
        for usage_row in usage_rows:
            reagent = usage_row.get("reagent_name")
            total_usage = float(usage_row.get("usage") or 0)
            if not reagent or total_usage <= 0:
                continue
            per_capita = (total_usage / source_students) if source_students else 0.0
            demand = round(per_capita * int(target_student_count or 0), 2)
            rows.append({
                "item_id": usage_row.get("item_id"),
                "item_name": usage_row.get("item_name") or "（未指定实验）",
                "reagent_name": reagent,
                "cas_number": meta.get(reagent, {}).get("cas_number"),
                "source_quantity": round(total_usage, 2),
                "per_capita_usage": round(per_capita, 4),
                "student_count": int(target_student_count or 0),
                "demand_quantity": demand,
                "purchase_quantity": demand,          # 课程单不扣库存，初值 = 需求量
                "current_stock": round(stock.get(reagent, 0.0), 2),
                "supplier": meta.get(reagent, {}).get("supplier"),
                "unit_price": meta.get(reagent, {}).get("unit_price"),
            })

        rows.sort(key=lambda r: (r["item_id"] is None, r["item_id"] or 0, r["reagent_name"]))
        return source_students, rows

    @handle_exception(context="预览课程采购单")
    def preview_course_plan(
        self,
        course_name: str,
        source_semester: str,
        target_student_count: int = DEFAULT_TARGET_STUDENT_COUNT
    ) -> ServiceResult:
        """预览（不落库）：人均用量与需求量"""
        source_students, rows = self.calculate_course_demand(
            course_name, source_semester, target_student_count
        )
        if not source_students and not rows:
            return ServiceResult.fail(
                message=f"未找到课程「{course_name}」在 {source_semester} 学年的数据或用量记录",
                error_code="NO_USAGE_DATA"
            )
        return ServiceResult.ok(
            data={
                "course_name": course_name,
                "source_semester": source_semester,
                "source_student_count": source_students,
                "target_student_count": int(target_student_count or 0),
                "items": rows,
            },
            message=f"共 {len(rows)} 条需求（历史人数 {source_students}）"
        )

    # ------------------------------------------------------------------
    # 生成 / 覆盖课程采购单
    # ------------------------------------------------------------------
    @handle_exception(context="生成课程采购单")
    def generate_course_plan(
        self,
        course_name: str,
        source_semester: str,
        target_semester: str,
        target_student_count: int = DEFAULT_TARGET_STUDENT_COUNT,
        created_by: Optional[str] = None
    ) -> ServiceResult:
        """生成课程采购单；同一课程 + 目标学年已存在则**覆盖**"""
        if not course_name or not source_semester or not target_semester:
            return ServiceResult.fail(
                message="课程名、来源学年、目标学年都必须填写",
                error_code="MISSING_PARAMETER"
            )

        source_students, rows = self.calculate_course_demand(
            course_name, source_semester, target_student_count
        )
        if not rows:
            return ServiceResult.fail(
                message=f"「{course_name}」在 {source_semester} 学年没有可用于预估的用量记录",
                error_code="NO_USAGE_DATA"
            )

        total_quantity = round(sum(r["demand_quantity"] for r in rows), 2)
        existing = purchase_plan_service.get_by_course(course_name, target_semester)

        from db.database import db

        try:
            with db.transaction():
                if existing:
                    plan_id = existing.id
                    plan_number = existing.plan_number
                    purchase_plan_service.update(plan_id, {
                        "source_semester": source_semester,
                        "source_student_count": source_students,
                        "target_student_count": int(target_student_count or 0),
                        "item_count": len(rows),
                        "total_quantity": total_quantity,
                        "updated_by": created_by,
                    })
                    purchase_plan_item_service.delete_by_plan(plan_id)
                    action = "已覆盖更新"
                else:
                    # 含微秒，避免同一秒内连续生成多份采购单时单号冲突
                    plan_number = "CP" + datetime.now().strftime("%Y%m%d%H%M%S%f")
                    plan_id = purchase_plan_service.create({
                        "plan_number": plan_number,
                        "course_name": course_name,
                        "source_semester": source_semester,
                        "target_semester": target_semester,
                        "source_student_count": source_students,
                        "target_student_count": int(target_student_count or 0),
                        "status": "待采购",
                        "item_count": len(rows),
                        "total_quantity": total_quantity,
                        "remark": f"按 {source_semester} 学年人均用量预估（{target_student_count} 人）",
                        "created_by": created_by,
                    })
                    action = "已生成"
                    if not plan_id:
                        raise RuntimeError("创建采购单失败")

                for row in rows:
                    created = purchase_plan_item_service.create({
                        "plan_id": plan_id,
                        "item_id": row["item_id"],
                        "item_name": row["item_name"],
                        "reagent_name": row["reagent_name"],
                        "cas_number": row["cas_number"],
                        "source_quantity": row["source_quantity"],
                        "per_capita_usage": row["per_capita_usage"],
                        "student_count": row["student_count"],
                        "demand_quantity": row["demand_quantity"],
                        "purchase_quantity": row["purchase_quantity"],
                        "current_stock": row["current_stock"],
                        "is_manual": 0,
                        "supplier": row["supplier"],
                        "unit_price": row["unit_price"],
                    })
                    if not created:
                        raise RuntimeError(f"创建采购明细失败：{row['reagent_name']}")

            logger.info(
                "课程采购单生成完成",
                course_name=course_name,
                plan_number=plan_number,
                action=action,
                item_count=len(rows)
            )
            return ServiceResult.ok(
                data={
                    "plan_id": plan_id,
                    "plan_number": plan_number,
                    "action": action,
                    "item_count": len(rows),
                    "total_quantity": total_quantity,
                },
                message=f"采购单 {plan_number} {action}（{len(rows)} 条需求）"
            )
        except Exception as e:
            logger.error("课程采购单生成失败，已回滚", error=str(e), exception=e)
            return ServiceResult.fail(message=f"生成采购单失败：{str(e)}")

    # ------------------------------------------------------------------
    # 管理员修改明细
    # ------------------------------------------------------------------
    @handle_exception(context="修改采购单明细")
    def update_plan_items(self, plan_id: int, updates: List[Dict], updated_by: Optional[str] = None) -> ServiceResult:
        """保存采购单明细的人工修改（需求量 / 采购量 / 供应商 / 备注）"""
        if not updates:
            return ServiceResult.fail(message="没有需要保存的修改", error_code="EMPTY_UPDATES")

        from db.database import db

        saved = 0
        try:
            with db.transaction():
                for row in updates:
                    item_id = row.get("id")
                    if not item_id:
                        continue
                    fields = {
                        "demand_quantity": row.get("demand_quantity"),
                        "purchase_quantity": row.get("purchase_quantity"),
                        "supplier": row.get("supplier"),
                        "remark": row.get("remark"),
                        "is_manual": 1,
                    }
                    if purchase_plan_item_service.update(item_id, fields):
                        saved += 1

                # 同步表头总量与修改人
                items = purchase_plan_item_service.get_by_plan(plan_id)
                total = round(sum(float(i.demand_quantity or 0) for i in items), 2)
                purchase_plan_service.update(plan_id, {
                    "total_quantity": total,
                    "updated_by": updated_by,
                })

            logger.info("采购单明细已保存", plan_id=plan_id, saved=saved)
            return ServiceResult.ok(data={"saved": saved}, message=f"已保存 {saved} 条修改")
        except Exception as e:
            logger.error("保存采购单明细失败，已回滚", error=str(e), exception=e)
            return ServiceResult.fail(message=f"保存失败：{str(e)}")

    # ------------------------------------------------------------------
    # 汇总（超管）
    # ------------------------------------------------------------------
    @handle_exception(context="汇总采购单")
    def summarize(self, target_semester: str) -> ServiceResult:
        """汇总某目标学年所有课程采购单：按试剂合并需求，再统一扣减一次库存"""
        if not target_semester:
            return ServiceResult.fail(message="请选择目标学年", error_code="MISSING_SEMESTER")

        plans = [
            p for p in purchase_plan_service.get_all_parsed()
            if p.target_semester == target_semester
        ]
        if not plans:
            return ServiceResult.ok(data=[], message=f"{target_semester} 学年还没有课程采购单")

        merged: Dict[str, Dict] = {}
        for plan in plans:
            for item in purchase_plan_item_service.get_by_plan(plan.id):
                reagent = item.reagent_name or "（未命名试剂）"
                entry = merged.setdefault(reagent, {
                    "reagent_name": reagent,
                    "cas_number": item.cas_number,
                    "total_demand": 0.0,
                    "courses": [],
                    "supplier": item.supplier,
                    "unit_price": item.unit_price,
                })
                demand = float(item.demand_quantity or 0)
                entry["total_demand"] += demand
                entry["courses"].append({
                    "course_name": plan.course_name,
                    "item_name": item.item_name or "（未指定实验）",
                    "demand": round(demand, 2),
                })

        stock = self._stock_by_reagent()

        rows: List[Dict] = []
        for reagent, entry in merged.items():
            total_demand = round(entry["total_demand"], 2)
            current_stock = round(stock.get(reagent, 0.0), 2)
            final_purchase = round(max(0.0, total_demand - current_stock), 2)
            rows.append({
                "reagent_name": reagent,
                "cas_number": entry["cas_number"],
                "total_demand": total_demand,
                "current_stock": current_stock,
                "final_purchase": final_purchase,
                "need_purchase": final_purchase > 0,
                "course_detail": sorted(entry["courses"], key=lambda x: x["demand"], reverse=True),
                "supplier": entry["supplier"],
                "unit_price": entry["unit_price"],
            })

        rows.sort(key=lambda r: r["final_purchase"], reverse=True)
        logger.info(
            "采购单汇总完成",
            target_semester=target_semester,
            plan_count=len(plans),
            reagent_count=len(rows)
        )
        return ServiceResult.ok(
            data=rows,
            message=f"已汇总 {len(plans)} 份课程采购单，共 {len(rows)} 种试剂"
        )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_plans(self, target_semester: Optional[str] = None) -> List:
        """采购单列表（可按目标学年筛选）"""
        plans = purchase_plan_service.get_all_parsed()
        if target_semester:
            plans = [p for p in plans if p.target_semester == target_semester]
        return plans

    def list_target_semesters(self) -> List[str]:
        """已存在采购单的目标学年（去重倒序）"""
        return sorted({p.target_semester for p in purchase_plan_service.get_all_parsed() if p.target_semester},
                      reverse=True)

    def get_plan_detail(self, plan_id: int) -> List[Dict]:
        """采购单明细（含实验名、人均用量等）"""
        return [
            {
                "id": item.id,
                "item_id": item.item_id,
                "item_name": item.item_name,
                "reagent_name": item.reagent_name,
                "cas_number": item.cas_number,
                "source_quantity": item.source_quantity,
                "per_capita_usage": item.per_capita_usage,
                "student_count": item.student_count,
                "demand_quantity": item.demand_quantity,
                "purchase_quantity": item.purchase_quantity,
                "current_stock": item.current_stock,
                "is_manual": item.is_manual,
                "supplier": item.supplier,
                "remark": item.remark,
            }
            for item in purchase_plan_item_service.get_by_plan(plan_id)
        ]


# 全局实例
purchase_service = PurchaseService()
