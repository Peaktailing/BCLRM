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
from business.experiment_plan_service import experiment_plan_business
from business.return_service import return_service
from models.core.borrow_order import (
    APPROVAL_APPROVED,
    APPROVAL_NOT_REQUIRED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    APPROVAL_WITHDRAWN,
    ITEM_STATUS_PENDING,
    ITEM_STATUS_RETURNED,
    ITEM_STATUS_FAILED,
    ORDER_STATUS_BORROWING,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_RETURNED,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_WITHDRAWN,
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
from utils.field_mapper import BorrowRecordField

# 允许发起工单的角色（管理员集合与权限服务保持一致）
ADMIN_ROLES = {"super_admin", "admin"}
TEACHER_ROLES = {"super_admin", "admin", "teacher"}


class WorkOrderService:
    """领用工单业务服务"""

    # ------------------------------------------------------------------
    # 审批人候选与角色辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _role_of(name: Optional[str]) -> Optional[str]:
        """查询人员角色（不在人员表中返回 None）"""
        if not name:
            return None
        for p in person_service.get_all_persons():
            if p.name == name:
                return getattr(p, "role", None)
        return None

    def _is_admin_plus(self, name: Optional[str]) -> bool:
        """管理员及以上（admin / super_admin）"""
        return self._role_of(name) in ADMIN_ROLES

    def is_super_admin(self, name: Optional[str]) -> bool:
        """是否超级管理员（用于页面候选标注「应急」与脏配置提示）"""
        return self._role_of(name) == "super_admin"

    def list_approver_candidates(self, exclude_name: Optional[str] = None) -> List[str]:
        """正常提交流程的合格审批人候选：管理员（admin）账号，排除发起人本人。

        超管不出现在该候选集中（超管接管唯一入口是管理员通过
        reassign_approver 应急改派，见 list_reassign_candidates）。
        """
        candidates = sorted({p.name for p in person_service.get_by_role("admin") if p.name})
        if exclude_name:
            candidates = [n for n in candidates if n != exclude_name]
        return candidates

    def list_reassign_candidates(self, exclude_name: Optional[str] = None) -> List[str]:
        """应急重新指定审批人的候选集：admin + super_admin。

        超管选项由页面标注「（应急）」；exclude_name 通常传工单申请人
        （新审批人不能是申请人本人）。
        """
        names = {p.name for p in person_service.get_by_role("admin") if p.name}
        names |= {p.name for p in person_service.get_by_role("super_admin") if p.name}
        if exclude_name:
            names.discard(exclude_name)
        return sorted(names)

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
        approver_name: Optional[str] = None,
    ) -> ServiceResult:
        """发起领用工单

        Args:
            order_type: 零星领用 / 课程领用
            applicant: 领用人
            cart_items: [{bottle_number, reagent_name, remaining_quantity}, ...]
            course: 课程对象（课程领用必填）
            exp_item: 实验项目对象（课程领用必填）
            approver_name: 审批人（显式指定；课程领用未指定时退回课程绑定审批人）。
                正常提交的合格审批人 = 管理员（admin）账号：排除超管、排除发起人本人；
                超管接管只能由管理员通过 reassign_approver 应急改派。
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
        course_approver = getattr(course, "approver", None) if course else None

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
            # 审批人：优先显式指定（页面下拉），课程领用未指定时退回课程绑定审批人。
            # 不再自动取第一个超管：正常提交的合格审批人 = 管理员（admin）账号，
            # 排除超管（超管接管唯一入口是管理员通过 reassign_approver 应急改派）。
            effective_approver = approver_name or course_approver
            if not effective_approver:
                return ServiceResult.fail(
                    message=(
                        "请指定审批人（清单含管控化学品："
                        + "、".join(sorted(controlled_types))
                        + "）；课程领用可先在「课程管理」为该课程指定审批管理员"
                    ),
                    error_code="NO_APPROVER",
                )
            if effective_approver == applicant:
                return ServiceResult.fail(
                    message=(
                        "审批人不能是发起人本人：请调整该课程的审批管理员，"
                        "或由其他管理员发起"
                    ),
                    error_code="SELF_APPROVAL",
                )
            _approver_role = self._role_of(effective_approver)
            if _approver_role == "super_admin":
                return ServiceResult.fail(
                    message=(
                        "请选择管理员审批；应急情况可由管理员通过"
                        "『重新指定审批人』改派超管接管"
                    ),
                    error_code="SUPER_ADMIN_APPROVER",
                )
            if _approver_role != "admin":
                return ServiceResult.fail(
                    message=(
                        f"审批人「{effective_approver}」不是管理员账号，"
                        "请选择管理员审批"
                    ),
                    error_code="INVALID_APPROVER_ROLE",
                )
            approver_name = effective_approver

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
            _operator = created_by or applicant
            _proxy = (
                f"；代 {applicant} 提交"
                if created_by and created_by != applicant
                else ""
            )
            audit(
                _operator,
                "提交审批",
                target_type="order",
                target_id=order_number,
                detail=(
                    f"含管控化学品（{'、'.join(sorted(controlled_types))}），"
                    f"等待 {approver_name} 审批" + _proxy
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
        order_number = "BO" + datetime.now().strftime("%Y%m%d%H%M%S%f")
        from db.database import db

        all_failed_msg = None
        try:
            # 领用扣库存与工单落库放在同一事务：任一环节失败则整体回滚，
            # 避免出现「已扣库存但没有工单记录 → 该瓶永远无法归还、用量丢失」的孤儿数据
            with db.transaction():
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
                    all_failed_msg = "领用失败：" + "；".join(failures)
                    raise RuntimeError(all_failed_msg)

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
            if all_failed_msg:
                return ServiceResult.fail(
                    message=all_failed_msg, error_code="ALL_ITEMS_FAILED"
                )
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
        _operator = created_by or applicant
        _proxy = (
            f"；代 {applicant} 提交"
            if created_by and created_by != applicant
            else ""
        )
        audit(
            _operator,
            "发起工单",
            target_type="order",
            target_id=order_number,
            detail=f"{order_type}，{len(success_items)} 瓶"
                   + (f"；{len(failures)} 瓶失败" if failures else "")
                   + _proxy,
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
        if not is_admin:
            # 非管理员只看本人工单；user_name 为空时返回空列表（避免鉴权被绕过）
            orders = [order for order in orders if order.applicant == (user_name or "")]
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
        """查找该「课程（+实验）」最近一次课程领用工单

        仅取实际执行过领用的工单（借用中/部分归还/已归还）：待审批/已驳回/
        已撤回从未扣库存，其明细数量不是真实历史用量，不能作为默认清单基准
        （QA 审查发现）。
        """
        _effective = (ORDER_STATUS_BORROWING, ORDER_STATUS_PARTIAL, ORDER_STATUS_RETURNED)
        orders = [
            order for order in borrow_order_service.get_all_parsed()
            if order.order_type == ORDER_TYPE_COURSE
            and order.course_name == course_name
            and (item_name is None or order.item_name == item_name)
            and getattr(order, "status", None) in _effective
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

        # 原子抢占：仅当审批状态仍为「待审批」时才写入「已批准」。
        # 先抢占再执行领用——败北方不扣库存。旧实现为先扣库存再无条件
        # 更新工单状态，撤回/重复审批并发时已撤回工单仍被执行领用、
        # 状态被互相覆盖（QA 审查发现）。
        claimed = borrow_order_service.update_where(
            {"id": order_id, "approval_status": APPROVAL_PENDING},
            {
                "status": ORDER_STATUS_BORROWING,
                "approval_status": APPROVAL_APPROVED,
                "approval_time": now,
                "approval_remark": remark,
            },
        )
        if not claimed:
            current = borrow_order_service.get_by_id(order_id)
            return ServiceResult.fail(
                message=(
                    "该工单已被其他会话处理（当前审批状态："
                    f"{getattr(current, 'approval_status', None) or '未知'}），请刷新后重试"
                ),
                error_code="APPROVAL_RACE_LOST",
            )

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
                # 审批信息按主键精确回写本次领用产生的流水（record_id 由
                # reagent_borrow 返回）。旧实现按「瓶号+领用人+时间窗」宽匹配，
                # 同瓶同人存在多张待审批工单时会互相覆盖审批留痕（QA 审查发现）
                _record_id = (result.data or {}).get("record_id")
                if _record_id:
                    borrow_record_service.update(_record_id, {
                        BorrowRecordField.APPROVER: approver_name,
                        BorrowRecordField.APPROVED: 1,
                    })
            else:
                # 批准时执行失败的明细置终态「执行失败」：该瓶从未借出，
                # 不得进入待还列表，否则按流程"归还"会凭空虚增库存（QA 审查发现）
                borrow_order_item_service.update(item.id, {"status": ITEM_STATUS_FAILED})
                failures.append(f"{item.bottle_number}：{result.message}")

        if success_count == 0:
            # 一瓶都没领成（库存状态已变化）：恢复待审批，提示发起人调整。
            # 明细保留「执行失败」终态，审批人重试时会重新逐瓶执行。
            borrow_order_service.update_where(
                {"id": order_id},
                {
                    "status": ORDER_STATUS_PENDING,
                    "approval_status": APPROVAL_PENDING,
                    "approval_time": None,
                    "approval_remark": None,
                },
            )
            return ServiceResult.fail(
                message="批准执行失败：" + "；".join(failures),
                error_code="APPROVE_EXECUTE_FAILED",
            )

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
        # 原子抢占：仅当审批状态仍为「待审批」才写入「已驳回」，
        # 防止撤回/批准并发时状态互相覆盖（QA 审查发现）
        if not borrow_order_service.update_where(
            {"id": order_id, "approval_status": APPROVAL_PENDING},
            {
                "status": ORDER_STATUS_REJECTED,
                "approval_status": APPROVAL_REJECTED,
                "approval_time": now,
                "approval_remark": remark,
            },
        ):
            current = borrow_order_service.get_by_id(order_id)
            return ServiceResult.fail(
                message=(
                    "该工单已被其他会话处理（当前审批状态："
                    f"{getattr(current, 'approval_status', None) or '未知'}），请刷新后重试"
                ),
                error_code="APPROVAL_RACE_LOST",
            )
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
    # 撤回 / 应急重新指定审批人
    # ------------------------------------------------------------------
    @handle_exception(context="撤回领用工单")
    def withdraw_order(
        self,
        order_id: int,
        operator: str,
        reason: Optional[str] = None
    ) -> ServiceResult:
        """撤回待审批工单（仅 PENDING；申请人本人或管理员及以上）

        Args:
            operator: 操作人（申请人本人或 admin+）
            reason: 撤回原因（可选）
        """
        order = borrow_order_service.get_by_id(order_id)
        if not order:
            return ServiceResult.fail(message="工单不存在", error_code="ORDER_NOT_FOUND")
        if order.approval_status != APPROVAL_PENDING:
            return ServiceResult.fail(
                message=f"该工单当前审批状态为「{order.approval_status}」，无法撤回",
                error_code="INVALID_APPROVAL_STATE",
            )
        if not (operator and order.applicant) or (
            operator != order.applicant and not self._is_admin_plus(operator)
        ):
            return ServiceResult.fail(
                message="只有申请人本人或管理员及以上可以撤回该工单",
                error_code="WITHDRAW_FORBIDDEN",
            )

        # 原子抢占：仅当审批状态仍为「待审批」才写入「已撤回」。
        # 旧实现先校验再无条件更新，审批人几乎同时点「批准」时双方都能通过
        # 校验，导致已撤回工单仍被执行领用（QA 审查发现）。
        if not borrow_order_service.update_where(
            {"id": order_id, "approval_status": APPROVAL_PENDING},
            {
                "status": ORDER_STATUS_WITHDRAWN,
                "approval_status": APPROVAL_WITHDRAWN,
                "approval_time": datetime.now().strftime("%Y/%m/%d %H:%M"),
                "approval_remark": reason or "申请人撤回",
            },
        ):
            current = borrow_order_service.get_by_id(order_id)
            return ServiceResult.fail(
                message=(
                    "该工单已被其他会话处理（当前审批状态："
                    f"{getattr(current, 'approval_status', None) or '未知'}），请刷新后重试"
                ),
                error_code="WITHDRAW_RACE_LOST",
            )
        for item in borrow_order_item_service.get_by_order(order_id):
            borrow_order_item_service.update(item.id, {"status": "已撤回"})

        logger.info(
            "工单已撤回",
            order_number=order.order_number,
            operator=operator,
        )

        from utils.audit import audit
        audit(
            operator,
            "撤回工单",
            target_type="order",
            target_id=order.order_number,
            detail=(reason or "（无原因）") + f"；原审批人 {order.approver or '—'}",
        )
        return ServiceResult.ok(
            data={"order_number": order.order_number},
            message=f"工单 {order.order_number} 已撤回",
        )

    @handle_exception(context="应急重新指定审批人")
    def reassign_approver(
        self,
        order_id: int,
        new_approver: str,
        operator: str,
        reason: Optional[str] = None
    ) -> ServiceResult:
        """应急重新指定待审批工单的审批人（仅 PENDING；仅管理员及以上可操作）

        这是超管接管的唯一正常入口：候选集 = admin + super_admin，
        新审批人不能是申请人本人。审计固定标记「应急重新指定审批人」。

        Args:
            new_approver: 新审批人（admin 或 super_admin 角色）
            operator: 操作人（必须为 admin+）
            reason: 改派原因（可选）
        """
        order = borrow_order_service.get_by_id(order_id)
        if not order:
            return ServiceResult.fail(message="工单不存在", error_code="ORDER_NOT_FOUND")
        if order.approval_status != APPROVAL_PENDING:
            return ServiceResult.fail(
                message=f"该工单当前审批状态为「{order.approval_status}」，无法重新指定审批人",
                error_code="INVALID_APPROVAL_STATE",
            )
        if not self._is_admin_plus(operator):
            return ServiceResult.fail(
                message="只有管理员及以上可以重新指定审批人",
                error_code="REASSIGN_FORBIDDEN",
            )
        if not new_approver:
            return ServiceResult.fail(
                message="请选择新的审批人", error_code="EMPTY_APPROVER"
            )
        if new_approver == order.applicant:
            return ServiceResult.fail(
                message="新审批人不能是申请人本人", error_code="SELF_APPROVAL"
            )
        if self._role_of(new_approver) not in ADMIN_ROLES:
            return ServiceResult.fail(
                message=f"新审批人「{new_approver}」不是管理员/超管账号",
                error_code="INVALID_APPROVER_ROLE",
            )

        old_approver = order.approver
        borrow_order_service.update(order_id, {"approver": new_approver})

        logger.info(
            "应急重新指定审批人",
            order_number=order.order_number,
            old_approver=old_approver,
            new_approver=new_approver,
            operator=operator,
        )

        from utils.audit import audit
        audit(
            operator,
            "应急重新指定审批人",
            target_type="order",
            target_id=order.order_number,
            detail=(
                f"审批人 {old_approver or '—'} → {new_approver}"
                f"（应急重新指定审批人）"
                + (f"；原因：{reason}" if reason else "")
            ),
        )
        return ServiceResult.ok(
            data={"order_number": order.order_number, "approver": new_approver},
            message=f"工单 {order.order_number} 审批人已改派为 {new_approver}",
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
            # 仅「待归还」明细可归还：跳过已归还及「执行失败」（该瓶从未借出）
            # 等终态，防止把未借出的瓶走归还路径造成库存虚增（QA 审查发现）
            if item.status != ITEM_STATUS_PENDING:
                continue

            remaining = float(item.borrow_qty or 0) - float(item.returned_qty or 0)
            qty = float(entry.get("return_qty") or 0)
            if qty < 0:
                failures.append(
                    f"{item.bottle_number}：归还量不能为负数"
                )
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
            # 空瓶必须由界面显式勾选确认，不再因「归还比例 0%」隐式触发
            # （比例 0 常是误拖，一旦隐式判空瓶即不可逆，会把整瓶用量全额计入）
            discard = bool(entry.get("discard"))
            target_remaining = 0.0 if discard else round(current + qty, 4)

            result = return_service.reagent_return(
                bottle_number=item.bottle_number,
                return_user=return_user,
                remaining_qty=target_remaining,
                as_empty=discard,
            )
            if result.is_success():
                done.append((item, qty))
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
        # 「执行失败」明细（批准时该瓶已被借走/耗尽等，从未实际借出）视为已了结，
        # 不阻塞工单在其余明细归还后正常闭环（QA 审查发现）
        all_items = borrow_order_item_service.get_by_order(order_id)
        if all_items and all(
            i.status in (ITEM_STATUS_RETURNED, ITEM_STATUS_FAILED) for i in all_items
        ):
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
