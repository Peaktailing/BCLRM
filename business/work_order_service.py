"""领用工单业务服务

两种工单：
- 零星领用：管理员及以上可发起，不关联课程 / 实验
- 课程领用：教师 + 管理员及以上可发起，关联「课程 + 实验」

流程：
- 发起工单：逐瓶调用 borrow_service.reagent_borrow（复用库存校验与扣减），
  成功的试剂写入工单明细
- 归还工单：先选工单，勾选要归还的试剂并填写各自归还量，
  逐项调用 return_service.reagent_return（归还后瓶内总量 = 当前剩余 + 归还量），
  成功后累加明细的已归还量并刷新工单状态

用量口径不变：用量 = 领用量 − 归还量（因此采购的人均预估无需调整）。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from business.borrow_service import borrow_service
from business.bottle_state import BorrowableStatus, ScrapStatus
from business.experiment_plan_service import experiment_plan_business
from business.return_service import return_service
from models.core.borrow_order import (
    APPROVAL_APPROVED,
    APPROVAL_NOT_REQUIRED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    ITEM_STATUS_PENDING,
    ITEM_STATUS_RETURNED,
    ORDER_STATUS_BORROWING,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_RETURNED,
    ORDER_STATUS_REJECTED,
    ORDER_TYPE_COURSE,
    ORDER_TYPE_SPORADIC,
)
from services.base.controlled_list_service import controlled_list_service
from services.base.experiment_course_service import experiment_course_service
from services.base.person_service import person_service
from services.core.borrow_order_service import (
    borrow_order_item_service,
    borrow_order_service,
)
from services.core.borrow_record_service import borrow_record_service
from services.core.reagent_bottle_service import reagent_bottle_service
from utils.error_handler import logger, ServiceResult, handle_exception
from utils.field_mapper import ReagentBottleField

# 允许发起工单的角色（管理员集合与权限服务保持一致）
ADMIN_ROLES = {"super_admin", "admin"}
TEACHER_ROLES = {"super_admin", "admin", "teacher"}


class WorkOrderService:
    """领用工单业务服务"""

    # ------------------------------------------------------------------
    # 发起工单
    # ------------------------------------------------------------------
    @handle_exception(context="发起领用工单")
    def create_order(
        self,
        order_type: str,
        applicant: str,
        cart_items: List[Dict],
        course=None,
        exp_item=None,
        remark: Optional[str] = None,
        created_by: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> ServiceResult:
        """发起领用工单

        Args:
            order_type: 零星领用 / 课程领用
            applicant: 领用人
            cart_items: [{bottle_number, reagent_name, remaining_quantity}, ...]
            course: 课程对象（课程领用必填）
            exp_item: 实验项目对象（课程领用必填）
        """
        if order_type not in (ORDER_TYPE_SPORADIC, ORDER_TYPE_COURSE):
            return ServiceResult.fail(message="工单类型不正确", error_code="INVALID_ORDER_TYPE")
        if not applicant:
            return ServiceResult.fail(message="请选择领用人", error_code="EMPTY_APPLICANT")
        if not cart_items:
            return ServiceResult.fail(message="领用清单为空", error_code="EMPTY_CART")
        if order_type == ORDER_TYPE_COURSE and (course is None or exp_item is None):
            return ServiceResult.fail(
                message="课程领用必须选择课程与实验项目",
                error_code="MISSING_COURSE_ITEM"
            )

        course_id = getattr(course, "id", None) if course else None
        item_id = getattr(exp_item, "id", None) if exp_item else None

        # ---------- 审批判定：任一试剂命中管控目录即需先审批 ----------
        needs_approval = False
        controlled_types = set()
        approver_name = getattr(course, "approver", None) if course else None

        for entry in cart_items:
            _bottle = reagent_bottle_service.get_by_bottle_number(
                entry.get("bottle_number")
            )
            _cas = getattr(_bottle, "cas_number", None) if _bottle else None
            if not _cas:
                continue
            _hit = controlled_list_service.get_by_cas_number(_cas)
            if _hit:
                needs_approval = True
                controlled_types.add(
                    getattr(_hit, "dangerous_type", None) or "管控化学品"
                )

        if needs_approval:
            # 审批人：课程领用取课程绑定的审批管理员；零星领用由超级管理员审批
            if not approver_name:
                _supers = sorted(
                    p.name for p in person_service.get_by_role("super_admin") if p.name
                )
                approver_name = _supers[0] if _supers else None
            if not approver_name:
                return ServiceResult.fail(
                    message=(
                        "清单含管控化学品（"
                        + "、".join(sorted(controlled_types))
                        + "），但尚无审批人：课程领用请先在「课程管理」为该课程"
                        "指定审批管理员；零星领用需要系统中存在超级管理员"
                    ),
                    error_code="NO_APPROVER",
                )
            if approver_name == applicant:
                return ServiceResult.fail(
                    message=(
                        "审批人不能是发起人本人：请调整该课程的审批管理员，"
                        "或由其他管理员发起"
                    ),
                    error_code="SELF_APPROVAL",
                )

            order_number = "BO" + datetime.now().strftime("%Y%m%d%H%M%S%f")
            from db.database import db

            try:
                with db.transaction():
                    order_id = borrow_order_service.create({
                        "order_number": order_number,
                        "order_type": order_type,
                        "applicant": applicant,
                        "borrow_time": datetime.now().strftime("%Y/%m/%d %H:%M"),
                        "course_id": course_id,
                        "item_id": item_id,
                        "course_name": getattr(course, "course_name", None) if course else None,
                        "item_name": getattr(exp_item, "item_name", None) if exp_item else None,
                        "project_id": project_id,
                        "status": ORDER_STATUS_PENDING,
                        "approval_status": APPROVAL_PENDING,
                        "approver": approver_name,
                        "remark": remark,
                        "created_by": created_by,
                    })
                    if not order_id:
                        raise RuntimeError("创建工单失败")
                    for entry in cart_items:
                        qty = entry.get("borrow_qty")
                        if qty is None:
                            qty = entry.get("remaining_quantity") or 0.1
                        try:
                            qty = float(qty)
                        except (TypeError, ValueError):
                            qty = 0.0
                        if not borrow_order_item_service.create({
                            "order_id": order_id,
                            "bottle_number": entry.get("bottle_number"),
                            "reagent_name": entry.get("reagent_name"),
                            "borrow_qty": qty,
                            "returned_qty": 0.0,
                            "status": "待审批",
                        }):
                            raise RuntimeError(
                                f"创建工单明细失败：{entry.get('bottle_number')}"
                            )
            except Exception as e:
                logger.error("创建待审批工单失败，已回滚", error=str(e), exception=e)
                return ServiceResult.fail(message=f"创建工单失败：{str(e)}")

            # 注意：此处不扣库存、不写领用流水，批准后由 approve_order 统一执行
            logger.info(
                "含管控试剂的工单已提交审批",
                order_number=order_number,
                approver=approver_name,
                controlled_types=sorted(controlled_types),
            )

            from utils.audit import audit
            audit(
                applicant,
                "提交审批",
                target_type="order",
                target_id=order_number,
                detail=(
                    f"含管控化学品（{'、'.join(sorted(controlled_types))}），"
                    f"等待 {approver_name} 审批"
                ),
            )
            return ServiceResult.ok(
                data={
                    "order_id": order_id,
                    "order_number": order_number,
                    "item_count": len(cart_items),
                    "failures": [],
                    "pending_approval": True,
                    "approver": approver_name,
                },
                message=(
                    f"工单 {order_number} 已提交审批（含："
                    + "、".join(sorted(controlled_types))
                    + f"），等待 {approver_name} 审批；批准后将自动完成领用"
                ),
            )

        # 无需审批：立即执行领用（扣库存）——原流程
        # 逐瓶领用（复用既有校验与库存扣减）
        success_items: List[Dict] = []
        failures: List[str] = []
        for entry in cart_items:
            bottle_number = entry.get("bottle_number")
            # 优先使用清单里显式填写的领用量（默认清单会带历史领用量），
            # 未填写时退回「整瓶剩余量」
            qty = entry.get("borrow_qty")
            if qty is None:
                qty = entry.get("remaining_quantity") or 0.1
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                qty = 0.0
            if qty <= 0:
                failures.append(f"{bottle_number}：领用量必须大于 0")
                continue
            result = borrow_service.reagent_borrow(
                bottle_number=bottle_number,
                user=applicant,
                borrow_qty=qty,
                course_id=course_id,
                item_id=item_id,
            )
            if result.is_success():
                success_items.append({
                    "bottle_number": bottle_number,
                    "reagent_name": entry.get("reagent_name"),
                    "borrow_qty": qty,
                    "returned_qty": 0.0,
                    "status": "待归还",
                })
            else:
                failures.append(f"{bottle_number}：{result.message}")

        if not success_items:
            return ServiceResult.fail(
                message="领用失败：" + "；".join(failures),
                error_code="ALL_ITEMS_FAILED"
            )

        order_number = "BO" + datetime.now().strftime("%Y%m%d%H%M%S%f")
        from db.database import db

        try:
            with db.transaction():
                order_id = borrow_order_service.create({
                    "order_number": order_number,
                    "order_type": order_type,
                    "applicant": applicant,
                    "borrow_time": datetime.now().strftime("%Y/%m/%d %H:%M"),
                    "course_id": course_id,
                    "item_id": item_id,
                    "course_name": getattr(course, "course_name", None) if course else None,
                    "item_name": getattr(exp_item, "item_name", None) if exp_item else None,
                    "project_id": project_id,
                    "status": ORDER_STATUS_BORROWING,
                    "approval_status": APPROVAL_NOT_REQUIRED,
                    "remark": remark,
                    "created_by": created_by,
                })
                if not order_id:
                    raise RuntimeError("创建工单失败")
                for item in success_items:
                    item["order_id"] = order_id
                    if not borrow_order_item_service.create(item):
                        raise RuntimeError(f"创建工单明细失败：{item['bottle_number']}")
        except Exception as e:
            logger.error("创建领用工单失败，已回滚", error=str(e), exception=e)
            return ServiceResult.fail(message=f"创建工单失败：{str(e)}")

        # 标记实验进度：已借出试剂（仅课程领用）
        if order_type == ORDER_TYPE_COURSE and course_id and item_id:
            marked_semester = getattr(course, "semester", None) or getattr(exp_item, "semester", None)
            experiment_plan_business.mark_borrowed(
                marked_semester,
                getattr(course, "course_name", None),
                getattr(exp_item, "item_name", None),
                borrow_time=datetime.now().strftime("%Y/%m/%d %H:%M"),
            )

        logger.info(
            "领用工单创建成功",
            order_number=order_number,
            order_type=order_type,
            item_count=len(success_items),
            failures=len(failures)
        )

        from utils.audit import audit
        audit(
            applicant,
            "发起工单",
            target_type="order",
            target_id=order_number,
            detail=f"{order_type}，{len(success_items)} 瓶"
                   + (f"；{len(failures)} 瓶失败" if failures else ""),
        )
        message = f"工单 {order_number} 已创建（{len(success_items)} 瓶试剂）"
        if failures:
            message += f"；{len(failures)} 瓶失败：" + "；".join(failures)
        return ServiceResult.ok(
            data={
                "order_id": order_id,
                "order_number": order_number,
                "item_count": len(success_items),
                "failures": failures,
            },
            message=message
        )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_open_orders(self, user_name: Optional[str] = None, is_admin: bool = False) -> List:
        """待归还的工单（借用中 / 部分归还）

        非管理员只能看到「领用人是本人」的工单（与还入权限一致）。
        """
        orders = [
            order for order in borrow_order_service.get_all_parsed()
            if order.status in (ORDER_STATUS_BORROWING, ORDER_STATUS_PARTIAL)
        ]
        if not is_admin and user_name:
            orders = [order for order in orders if order.applicant == user_name]
        return orders

    def list_orders(self, user_name: Optional[str] = None, is_admin: bool = False) -> List:
        """全部工单（非管理员只看自己的）"""
        orders = borrow_order_service.get_all_parsed()
        if not is_admin and user_name:
            orders = [order for order in orders if order.applicant == user_name]
        return orders

    def get_order_items(self, order_id: int) -> List[Dict]:
        """工单明细（含未归还量）"""
        rows = []
        for item in borrow_order_item_service.get_by_order(order_id):
            borrow_qty = float(item.borrow_qty or 0)
            returned_qty = float(item.returned_qty or 0)
            rows.append({
                "id": item.id,
                "bottle_number": item.bottle_number,
                "reagent_name": item.reagent_name,
                "borrow_qty": borrow_qty,
                "returned_qty": returned_qty,
                "remaining_qty": round(max(0.0, borrow_qty - returned_qty), 4),
                "status": item.status,
            })
        return rows

    # ------------------------------------------------------------------
    # 历史工单 → 默认领用清单
    # ------------------------------------------------------------------
    def find_latest_history_order(self, course_name: str, item_name: Optional[str] = None):
        """查找该「课程（+实验）」最近一次课程领用工单"""
        orders = [
            order for order in borrow_order_service.get_all_parsed()
            if order.order_type == ORDER_TYPE_COURSE
            and order.course_name == course_name
            and (item_name is None or order.item_name == item_name)
        ]
        if not orders:
            return None
        orders.sort(key=lambda o: getattr(o, "borrow_time", "") or "", reverse=True)
        return orders[0]

    @handle_exception(context="生成默认领用清单")
    def build_default_cart(
        self,
        course_name: str,
        item_name: Optional[str] = None
    ) -> ServiceResult:
        """按历史工单生成默认领用清单

        取该「课程（+实验）」最近一次课程领用工单的明细，按**试剂名称**在当前
        库存中匹配可借试剂瓶，生成一份可直接使用、可再调整的领用清单
        （领用量沿用历史值，可在页面上修改）。

        Returns:
            ServiceResult.data = {order_number, borrow_time, cart, missing}
        """
        history = self.find_latest_history_order(course_name, item_name)
        if history is None:
            return ServiceResult.fail(
                message="该课程（实验）没有历史领用工单，无法生成默认清单",
                error_code="NO_HISTORY_ORDER"
            )

        history_items = borrow_order_item_service.get_by_order(history.id)
        if not history_items:
            return ServiceResult.fail(
                message="历史工单没有明细", error_code="EMPTY_HISTORY"
            )

        # 当前可借试剂瓶索引：试剂名 -> [瓶...]
        available: Dict[str, List] = defaultdict(list)
        for bottle in reagent_bottle_service.get_all_parsed():
            name = getattr(bottle, "reagent_name", None)
            if not name:
                continue
            if getattr(bottle, "borrowable_flag", None) != "可借":
                continue
            if float(getattr(bottle, "remaining_quantity", 0) or 0) <= 0:
                continue
            available[name].append(bottle)

        cart: List[Dict] = []
        missing: List[str] = []
        for item in history_items:
            name = item.reagent_name
            pool = available.get(name) or []
            if not pool:
                missing.append(name or "（未命名试剂）")
                continue
            bottle = pool.pop(0)
            cart.append({
                "bottle_number": getattr(bottle, "bottle_number", None),
                "reagent_name": getattr(bottle, "reagent_name", None) or name,
                "cas_number": getattr(bottle, "cas_number", None),
                "specification": getattr(bottle, "specification", None),
                "remaining_quantity": getattr(bottle, "remaining_quantity", None),
                "borrow_qty": float(item.borrow_qty or 0),
                "history_qty": float(item.borrow_qty or 0),
            })

        message = (
            f"已按历史工单 {history.order_number}"
            f"（{history.borrow_time or '时间未知'}）生成 {len(cart)} 条清单"
        )
        if missing:
            message += f"；{len(missing)} 种试剂当前无可借库存：{'、'.join(missing)}"

        logger.info(
            "生成默认领用清单",
            course_name=course_name,
            item_name=item_name,
            history_order=history.order_number,
            cart_count=len(cart),
            missing_count=len(missing)
        )
        return ServiceResult.ok(
            data={
                "order_number": history.order_number,
                "borrow_time": history.borrow_time,
                "cart": cart,
                "missing": missing,
            },
            message=message
        )

    def can_return(self, order, user_name: Optional[str], is_admin: bool) -> bool:
        """还入权限：管理员及以上，或该工单的原领用人"""
        if is_admin:
            return True
        return bool(order and user_name and order.applicant == user_name)

    # ------------------------------------------------------------------
    # 工单审批（仅含管控试剂的工单需要）
    # ------------------------------------------------------------------
    @staticmethod
    def _order_semester(order):
        """从工单关联课程取学年（用于实验进度标记）"""
        if getattr(order, "course_id", None):
            _course = experiment_course_service.get_by_id(order.course_id)
            return getattr(_course, "semester", None) if _course else None
        return None

    def list_pending_approvals(self, approver_name: Optional[str] = None) -> List:
        """待审批工单列表（可按审批人过滤）"""
        orders = [
            order for order in borrow_order_service.get_all_parsed()
            if order.approval_status == APPROVAL_PENDING
        ]
        if approver_name:
            orders = [o for o in orders if o.approver == approver_name]
        return orders

    def can_approve(self, order, user_name: Optional[str], is_admin: bool = False) -> bool:
        """审批权限：仅该工单指定的审批人（超管也不代办，保证审批留痕）"""
        if not (order and user_name):
            return False
        return order.approver == user_name

    @handle_exception(context="审批领用工单")
    def approve_order(
        self,
        order_id: int,
        approver_name: str,
        remark: Optional[str] = None
    ) -> ServiceResult:
        """批准工单并执行领用（此时才真正扣库存、写领用流水）

        Args:
            approver_name: 审批人（必须与工单指定的审批人一致）
        """
        order = borrow_order_service.get_by_id(order_id)
        if not order:
            return ServiceResult.fail(message="工单不存在", error_code="ORDER_NOT_FOUND")
        if order.approval_status != APPROVAL_PENDING:
            return ServiceResult.fail(
                message=f"该工单当前审批状态为「{order.approval_status}」，无法审批",
                error_code="INVALID_APPROVAL_STATE",
            )
        if not self.can_approve(order, approver_name):
            return ServiceResult.fail(
                message=f"只有指定审批人「{order.approver}」可以审批该工单",
                error_code="NOT_ASSIGNED_APPROVER",
            )

        items = borrow_order_item_service.get_by_order(order_id)
        now = datetime.now().strftime("%Y/%m/%d %H:%M")

        success_count = 0
        failures: List[str] = []
        for item in items:
            result = borrow_service.reagent_borrow(
                bottle_number=item.bottle_number,
                user=order.applicant,
                borrow_qty=float(item.borrow_qty or 0),
                course_id=order.course_id,
                item_id=order.item_id,
            )
            if result.is_success():
                success_count += 1
                borrow_order_item_service.update(item.id, {"status": ITEM_STATUS_PENDING})
                # 审批信息回写领用流水（approver / approved 字段落地）
                borrow_record_service.update_by_field(
                    "bottle_number", item.bottle_number,
                    {"approver": approver_name, "approved": True},
                )
            else:
                failures.append(f"{item.bottle_number}：{result.message}")

        if success_count == 0:
            # 一瓶都没领成（库存状态已变化）：保持待审批，提示发起人调整
            return ServiceResult.fail(
                message="批准执行失败：" + "；".join(failures),
                error_code="APPROVE_EXECUTE_FAILED",
            )

        borrow_order_service.update(order_id, {
            "status": ORDER_STATUS_BORROWING,
            "approval_status": APPROVAL_APPROVED,
            "approval_time": now,
            "approval_remark": remark,
        })

        # 标记实验进度：已借出试剂（仅课程领用）
        if order.course_name and order.item_name:
            experiment_plan_business.mark_borrowed(
                self._order_semester(order),
                order.course_name,
                order.item_name,
                borrow_time=now,
            )

        logger.info(
            "工单审批通过并完成领用",
            order_number=order.order_number,
            approver=approver_name,
            success_count=success_count,
            failures=len(failures),
        )

        from utils.audit import audit
        audit(
            approver_name,
            "审批通过",
            target_type="order",
            target_id=order.order_number,
            detail=f"批准 {success_count} 瓶领用" + (f"；意见：{remark}" if remark else ""),
        )
        message = f"工单 {order.order_number} 审批通过，已完成 {success_count} 瓶领用"
        if failures:
            message += "；失败：" + "；".join(failures)
        return ServiceResult.ok(
            data={"approved": success_count, "failures": failures},
            message=message,
        )

    @handle_exception(context="驳回领用工单")
    def reject_order(
        self,
        order_id: int,
        approver_name: str,
        remark: Optional[str] = None
    ) -> ServiceResult:
        """驳回工单（不扣库存，工单关闭）"""
        order = borrow_order_service.get_by_id(order_id)
        if not order:
            return ServiceResult.fail(message="工单不存在", error_code="ORDER_NOT_FOUND")
        if order.approval_status != APPROVAL_PENDING:
            return ServiceResult.fail(
                message=f"该工单当前审批状态为「{order.approval_status}」，无法审批",
                error_code="INVALID_APPROVAL_STATE",
            )
        if not self.can_approve(order, approver_name):
            return ServiceResult.fail(
                message=f"只有指定审批人「{order.approver}」可以审批该工单",
                error_code="NOT_ASSIGNED_APPROVER",
            )

        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        borrow_order_service.update(order_id, {
            "status": ORDER_STATUS_REJECTED,
            "approval_status": APPROVAL_REJECTED,
            "approval_time": now,
            "approval_remark": remark,
        })
        for item in borrow_order_item_service.get_by_order(order_id):
            borrow_order_item_service.update(item.id, {"status": "已驳回"})

        logger.info(
            "工单已驳回",
            order_number=order.order_number,
            approver=approver_name,
        )

        from utils.audit import audit
        audit(
            approver_name,
            "驳回工单",
            target_type="order",
            target_id=order.order_number,
            detail=remark or "（无意见）",
        )
        return ServiceResult.ok(
            data={"order_number": order.order_number},
            message=f"工单 {order.order_number} 已驳回",
        )

    # ------------------------------------------------------------------
    # 归还工单
    # ------------------------------------------------------------------
    @handle_exception(context="按工单归还")
    def return_items(
        self,
        order_id: int,
        returns: List[Dict],
        return_user: str,
        close_items: bool = True
    ) -> ServiceResult:
        """按工单归还

        Args:
            order_id: 工单ID
            returns: [{"item_id": 工单明细ID, "return_qty": 归还量}, ...]
            return_user: 归还人
            close_items: 是否「结清」已提交归还的明细。
                True（默认）：只要提交了归还，该明细即视为「已归还」，
                    未还回的差额计为实际使用量，不再重复出现在待还列表；
                False：严格模式，须还满领用量才结清。
        """
        order = borrow_order_service.get_by_id(order_id)
        if not order:
            return ServiceResult.fail(message="工单不存在", error_code="ORDER_NOT_FOUND")

        items = {item.id: item for item in borrow_order_item_service.get_by_order(order_id)}
        done: List[tuple] = []
        failures: List[str] = []

        for entry in returns:
            item = items.get(entry.get("item_id"))
            if item is None:
                continue
            if item.status == ITEM_STATUS_RETURNED:
                continue

            remaining = float(item.borrow_qty or 0) - float(item.returned_qty or 0)
            qty = float(entry.get("return_qty") or 0)
            if qty < 0:
                continue
            if qty > remaining + 1e-6:
                failures.append(
                    f"{item.bottle_number}：归还量 {qty:g} 超过未归还量 {remaining:g}"
                )
                continue

            bottle = reagent_bottle_service.get_by_bottle_number(item.bottle_number)
            current = float(getattr(bottle, "remaining_quantity", 0) or 0) if bottle else 0.0

            # 归还比例 0%（或显式 discard）：视为「空瓶」——
            # 不还回试剂，归还后瓶中余量记 0，并把该瓶移入待报废清单
            discard = bool(entry.get("discard")) or qty <= 0
            target_remaining = 0.0 if discard else round(current + qty, 4)

            result = return_service.reagent_return(
                bottle_number=item.bottle_number,
                return_user=return_user,
                remaining_qty=target_remaining,
            )
            if result.is_success():
                done.append((item, qty))
                if discard and bottle is not None:
                    reagent_bottle_service.update(bottle.id, {
                        ReagentBottleField.BORROWABLE_FLAG: BorrowableStatus.EMPTY,
                        ReagentBottleField.SCRAP_FLAG: ScrapStatus.PENDING,
                    })
            else:
                failures.append(f"{item.bottle_number}：{result.message}")

        if not done:
            return ServiceResult.fail(
                message="归还失败：" + ("；".join(failures) if failures else "没有可归还的试剂"),
                error_code="NO_ITEM_RETURNED"
            )

        # 累加已归还量并刷新明细状态
        for item, qty in done:
            new_returned = float(item.returned_qty or 0) + qty
            if close_items:
                # 已提交归还的明细直接结清：
                # 未还回的差额计为「实际使用量」，不再重复出现在待还列表
                status = ITEM_STATUS_RETURNED
            else:
                status = (
                    ITEM_STATUS_RETURNED
                    if new_returned + 1e-6 >= float(item.borrow_qty or 0)
                    else ITEM_STATUS_PENDING
                )
            borrow_order_item_service.update(item.id, {
                "returned_qty": round(new_returned, 4),
                "status": status,
            })

        # 刷新工单整体状态
        all_items = borrow_order_item_service.get_by_order(order_id)
        if all_items and all(i.status == ITEM_STATUS_RETURNED for i in all_items):
            new_status = ORDER_STATUS_RETURNED
        elif any(
            i.status == ITEM_STATUS_RETURNED or float(i.returned_qty or 0) > 0
            for i in all_items
        ):
            # 任一明细已结清（含空瓶归还）或已还回一部分，即视为「部分归还」
            new_status = ORDER_STATUS_PARTIAL
        else:
            new_status = ORDER_STATUS_BORROWING
        borrow_order_service.update(order_id, {"status": new_status})

        # 标记实验进度：全部归还后记为「已还入试剂」（仅课程领用）
        if order.course_name and order.item_name and new_status == ORDER_STATUS_RETURNED:
            marked_semester = None
            if order.course_id:
                _course = experiment_course_service.get_by_id(order.course_id)
                marked_semester = getattr(_course, "semester", None) if _course else None
            experiment_plan_business.mark_returned(
                marked_semester,
                order.course_name,
                order.item_name,
                return_time=datetime.now().strftime("%Y/%m/%d %H:%M"),
            )

        logger.info(
            "工单归还完成",
            order_number=order.order_number,
            returned_count=len(done),
            status=new_status
        )

        from utils.audit import audit
        audit(
            return_user,
            "工单归还",
            target_type="order",
            target_id=order.order_number,
            detail=f"归还 {len(done)} 瓶，工单状态：{new_status}",
        )

        # 写入实验试剂用量台账（course/item/project 维度，供统计与留痕）
        try:
            from services.base.experiment_project_service import (
                experiment_reagent_usage_service,
            )
            _usage_semester = self._order_semester(order)
            _usage_time = datetime.now().strftime("%Y/%m/%d %H:%M")
            for item, qty in done:
                _bottle = reagent_bottle_service.get_by_bottle_number(item.bottle_number)
                experiment_reagent_usage_service.add_usage({
                    "project_id": getattr(order, "project_id", None),
                    "reagent_name": item.reagent_name,
                    "cas_number": getattr(_bottle, "cas_number", None) if _bottle else None,
                    "usage_quantity": qty,
                    "usage_date": _usage_time,
                    "course_name": order.course_name,
                    "item_name": order.item_name,
                    "semester": _usage_semester,
                })
        except Exception as e:
            logger.error("用量台账写入失败", error=str(e), exception=e)
        message = f"工单 {order.order_number} 已归还 {len(done)} 瓶，当前状态：{new_status}"
        if failures:
            message += "；部分失败：" + "；".join(failures)
        return ServiceResult.ok(
            data={"returned": len(done), "status": new_status, "failures": failures},
            message=message
        )


# 全局实例
work_order_service = WorkOrderService()
