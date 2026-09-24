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
from models.base.purchase_order import (
    PO_ORDERED,
    PO_PENDING,
    PO_RECEIVED,
    RESERVATION_APPROVED,
    RESERVATION_FULFILLED,
    RESERVATION_PENDING,
    RESERVATION_REJECTED,
)
from services.base.controlled_list_service import controlled_list_service
from services.base.reservation_purchase_service import (
    purchase_order_service,
    reservation_order_service,
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
    # ------------------------------------------------------------------
    # 采购审批（含管控化学品的采购需管理员审批）
    # ------------------------------------------------------------------
    @staticmethod
    def _plan_has_controlled(plan_id: int) -> bool:
        """判断采购单是否含管控化学品（按明细 CAS 匹配管控目录）"""
        for item in purchase_plan_item_service.get_by_plan(plan_id):
            cas = getattr(item, "cas_number", None)
            if cas and controlled_list_service.get_by_cas_number(cas):
                return True
        return False

    @handle_exception(context="提交采购审批")
    def submit_for_approval(
        self, plan_id: int, approver: str, submitted_by: str
    ) -> ServiceResult:
        """提交采购单进入审批流（含管控化学品时必须经审批）"""
        plan = purchase_plan_service.get_by_id(plan_id)
        if not plan:
            return ServiceResult.fail(message="采购单不存在", error_code="PLAN_NOT_FOUND")
        if (plan.approval_status or "") == "待审批":
            return ServiceResult.fail(
                message="该采购单已在审批中", error_code="ALREADY_PENDING"
            )
        if not self._plan_has_controlled(plan_id):
            return ServiceResult.fail(
                message="该采购单不含管控化学品，无需审批，可直接执行采购",
                error_code="NO_CONTROLLED_ITEM",
            )
        if not approver or approver == submitted_by:
            return ServiceResult.fail(
                message="请指定审批人（不能是发起人本人）",
                error_code="INVALID_APPROVER",
            )

        if purchase_plan_service.update(plan_id, {
            "approval_status": "待审批",
            "approver": approver,
            "approval_time": None,
            "approval_remark": None,
        }):
            logger.info(
                "采购单已提交审批",
                plan_number=plan.plan_number, approver=approver
            )
            return ServiceResult.ok(message=f"采购单已提交，等待 {approver} 审批")
        return ServiceResult.fail(message="提交失败，请重试")

    def list_pending_purchase_approvals(self, approver_name: Optional[str] = None) -> List:
        """待审批采购单（可按审批人过滤）"""
        plans = [
            p for p in purchase_plan_service.get_all_parsed()
            if (p.approval_status or "") == "待审批"
        ]
        if approver_name:
            plans = [p for p in plans if p.approver == approver_name]
        return plans

    def can_approve_purchase(self, plan, user_name: Optional[str]) -> bool:
        """仅采购单指定的审批人可审批"""
        return bool(plan and user_name and plan.approver == user_name)

    @handle_exception(context="审批采购单")
    def approve_purchase(
        self, plan_id: int, approver_name: str, remark: Optional[str] = None
    ) -> ServiceResult:
        """批准采购单（批准后可执行采购/入库）"""
        plan = purchase_plan_service.get_by_id(plan_id)
        if not plan:
            return ServiceResult.fail(message="采购单不存在", error_code="PLAN_NOT_FOUND")
        if (plan.approval_status or "") != "待审批":
            return ServiceResult.fail(
                message=f"该采购单审批状态为「{plan.approval_status}」，无法审批",
                error_code="INVALID_APPROVAL_STATE",
            )
        if not self.can_approve_purchase(plan, approver_name):
            return ServiceResult.fail(
                message=f"只有指定审批人「{plan.approver}」可以审批该采购单",
                error_code="NOT_ASSIGNED_APPROVER",
            )

        if purchase_plan_service.update(plan_id, {
            "approval_status": "已批准",
            "approval_time": datetime.now().strftime("%Y/%m/%d %H:%M"),
            "approval_remark": remark,
        }):
            logger.info(
                "采购单审批通过",
                plan_number=plan.plan_number, approver=approver_name
            )
            return ServiceResult.ok(message=f"采购单 {plan.plan_number} 审批通过")
        return ServiceResult.fail(message="审批保存失败，请重试")

    @handle_exception(context="驳回采购单")
    def reject_purchase(
        self, plan_id: int, approver_name: str, remark: Optional[str] = None
    ) -> ServiceResult:
        """驳回采购单"""
        plan = purchase_plan_service.get_by_id(plan_id)
        if not plan:
            return ServiceResult.fail(message="采购单不存在", error_code="PLAN_NOT_FOUND")
        if (plan.approval_status or "") != "待审批":
            return ServiceResult.fail(
                message=f"该采购单审批状态为「{plan.approval_status}」，无法审批",
                error_code="INVALID_APPROVAL_STATE",
            )
        if not self.can_approve_purchase(plan, approver_name):
            return ServiceResult.fail(
                message=f"只有指定审批人「{plan.approver}」可以审批该采购单",
                error_code="NOT_ASSIGNED_APPROVER",
            )

        if purchase_plan_service.update(plan_id, {
            "approval_status": "已驳回",
            "approval_time": datetime.now().strftime("%Y/%m/%d %H:%M"),
            "approval_remark": remark,
        }):
            logger.info("采购单已驳回", plan_number=plan.plan_number, approver=approver_name)
            return ServiceResult.ok(message=f"采购单 {plan.plan_number} 已驳回")
        return ServiceResult.fail(message="驳回保存失败，请重试")

    # ------------------------------------------------------------------
    # 预定单（库存不足时提前预定 → 审批 → 转采购单）
    # ------------------------------------------------------------------
    @handle_exception(context="创建预定单")
    def create_reservation(
        self,
        reagent_name: str,
        quantity: float,
        applicant: str,
        cas_number: Optional[str] = None,
        unit: str = "g",
        semester: Optional[str] = None,
    ) -> ServiceResult:
        """提交试剂预定单（状态 pending，等待管理员审批）"""
        if not reagent_name or not str(reagent_name).strip():
            return ServiceResult.fail(message="请填写试剂名称", error_code="INVALID_RESERVATION")
        if quantity is None or float(quantity) <= 0:
            return ServiceResult.fail(message="预定数量必须大于 0", error_code="INVALID_RESERVATION")
        order_number = "RES" + datetime.now().strftime("%Y%m%d%H%M%S%f")
        rid = reservation_order_service.create({
            "order_number": order_number,
            "semester": semester,
            "reagent_name": str(reagent_name).strip(),
            "cas_number": cas_number,
            "quantity": float(quantity),
            "unit": unit or "g",
            "applicant": applicant,
            "status": RESERVATION_PENDING,
        })
        if rid:
            logger.info("预定单已创建", order_number=order_number, applicant=applicant)
            from utils.audit import audit
            audit(applicant, "提交预定", target_type="reservation", target_id=order_number,
                  detail=f"{reagent_name} × {quantity}{unit or 'g'}")
            return ServiceResult.ok(
                data={"reservation_id": rid, "order_number": order_number},
                message=f"预定单 {order_number} 已提交，等待管理员审批",
            )
        return ServiceResult.fail(message="预定失败，请重试")

    @handle_exception(context="审批预定单")
    def review_reservation(
        self, reservation_id: int, approve: bool, reviewer: str,
        remark: Optional[str] = None
    ) -> ServiceResult:
        """审批预定单（批准 / 驳回）"""
        res = reservation_order_service.get_by_id(reservation_id)
        if not res:
            return ServiceResult.fail(message="预定单不存在", error_code="NOT_FOUND")
        if res.status != RESERVATION_PENDING:
            return ServiceResult.fail(
                message=(
                    f"该预定单状态为「{reservation_order_service.status_label(res.status)}」，"
                    "无法审批"
                ),
                error_code="INVALID_STATE",
            )
        new_status = RESERVATION_APPROVED if approve else RESERVATION_REJECTED
        if reservation_order_service.update(reservation_id, {"status": new_status}):
            from utils.audit import audit
            audit(
                reviewer,
                "预定审批通过" if approve else "驳回预定",
                target_type="reservation",
                target_id=res.order_number,
                detail=remark or "",
            )
            return ServiceResult.ok(
                message=(
                    f"预定单 {res.order_number} 已{'批准' if approve else '驳回'}"
                )
            )
        return ServiceResult.fail(message="审批保存失败，请重试")

    @handle_exception(context="预定单转采购单")
    def convert_reservation_to_purchase_order(
        self,
        reservation_id: int,
        supplier: Optional[str] = None,
        unit_price: Optional[float] = None,
        created_by: Optional[str] = None,
    ) -> ServiceResult:
        """把「已批准」的预定单转为正式采购单（待下单）"""
        res = reservation_order_service.get_by_id(reservation_id)
        if not res:
            return ServiceResult.fail(message="预定单不存在", error_code="NOT_FOUND")
        if res.status != RESERVATION_APPROVED:
            return ServiceResult.fail(
                message="仅「已批准」的预定单可转为采购单",
                error_code="INVALID_STATE",
            )
        order_number = "PO" + datetime.now().strftime("%Y%m%d%H%M%S%f")
        po_id = purchase_order_service.create({
            "order_number": order_number,
            "reservation_order_id": reservation_id,
            "reagent_name": res.reagent_name,
            "cas_number": res.cas_number,
            "order_quantity": res.quantity,
            "unit_price": unit_price,
            "supplier": supplier,
            "status": PO_PENDING,
        })
        if po_id:
            reservation_order_service.update(reservation_id, {"status": RESERVATION_FULFILLED})
            from utils.audit import audit
            audit(
                created_by, "预定转采购",
                target_type="purchase_order", target_id=order_number,
                detail=f"来源预定单 {res.order_number}",
            )
            return ServiceResult.ok(message=f"已生成采购单 {order_number}（待下单）")
        return ServiceResult.fail(message="生成采购单失败，请重试")

    # ------------------------------------------------------------------
    # 采购单状态流转（待下单 → 已下单 → 已到货）
    # ------------------------------------------------------------------
    @handle_exception(context="更新采购单状态")
    def update_purchase_order_status(
        self, po_id: int, new_status: str, operator: Optional[str] = None
    ) -> ServiceResult:
        po = purchase_order_service.get_by_id(po_id)
        if not po:
            return ServiceResult.fail(message="采购单不存在", error_code="NOT_FOUND")
        allowed = {
            PO_PENDING: {PO_ORDERED, "cancelled"},
            PO_ORDERED: {PO_RECEIVED, "cancelled"},
            PO_RECEIVED: set(),
            "cancelled": set(),
        }
        if new_status not in allowed.get(po.status or "", set()):
            return ServiceResult.fail(
                message=(
                    f"不允许从「{purchase_order_service.status_label(po.status)}」"
                    f"变更为「{purchase_order_service.status_label(new_status)}」"
                ),
                error_code="INVALID_TRANSITION",
            )
        if purchase_order_service.update(po_id, {"status": new_status}):
            from utils.audit import audit
            audit(
                operator, "采购单状态",
                target_type="purchase_order", target_id=po.order_number,
                detail=(
                    f"{purchase_order_service.status_label(po.status)} → "
                    f"{purchase_order_service.status_label(new_status)}"
                ),
            )
            msg = (
                f"采购单 {po.order_number} → "
                f"{purchase_order_service.status_label(new_status)}"
            )
            if new_status == PO_RECEIVED:
                msg += "；请到「试剂入库」完成入库"
            return ServiceResult.ok(message=msg)
        return ServiceResult.fail(message="更新失败，请重试")


# 全局实例
purchase_service = PurchaseService()
