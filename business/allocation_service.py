"""智能分配 / 需求调配业务服务

职责：
1. 智能分配（plan）：给定「试剂 + 需求量 + 需求人」，从可借试剂瓶中按优先级
   挑选，优先级 = 本人 → 本教研室（person.department 相同）→ 全院；
   并按「当前管理人」分组，供后续拆分调配单。
2. 智能计算：按本年度需求量与存量，提示存量是否够用（仅供管理员决策参考）。
3. 生成调配单：每个管理人一张调配单，发到对应管理员手上。
4. 处理调配单：管理员决定「借出 / 退回」。
   - 借出 = **管理权流转**：把试剂管理权转到需求人手里（不同管理员之间流转试剂），
     并写入一条管理人变更记录；
   - 退回即驳回该调配单。

注意：这与现有「借用（领用/归还）」是两条独立链路——借用不改变管理人。
"""
from datetime import datetime
from typing import List, Optional, Dict, Any

from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.allocation_order_service import (
    allocation_order_service,
    allocation_order_item_service,
)
from services.core.reagent_demand_service import (
    reagent_demand_service,
    reagent_demand_item_service,
)
from services.base.person_service import person_service
from business.manager_service import manager_service, REASON_ALLOCATION
from business.bottle_state import is_borrowable, is_expired
from models.core.allocation_order import (
    ALLOC_STATUS_PENDING,
    ALLOC_STATUS_LENT,
    ALLOC_STATUS_REJECTED,
    ALLOC_ITEM_PENDING,
    ALLOC_ITEM_LENT,
    ALLOC_ITEM_REJECTED,
)
from models.core.reagent_demand import (
    DEMAND_STATUS_PENDING,
    DEMAND_STATUS_DONE,
    DEMAND_STATUS_PARTIAL,
    DEMAND_STATUS_REJECTED,
)
from utils.field_mapper import (
    ReagentBottleField,
    AllocationOrderField,
    AllocationOrderItemField,
    ReagentDemandField,
)
from utils.id_generator import id_generator
from utils.error_handler import logger, ServiceResult, handle_exception
from utils.audit import audit
from db.database import db

# 未指定管理人时的占位标签
UNASSIGNED_MANAGER = "（未指定管理人）"

# 分配优先级
PRIORITY_SELF = 0        # 本人
PRIORITY_DEPARTMENT = 1  # 本教研室
PRIORITY_INSTITUTE = 2   # 全院


class AllocationService:
    """智能分配 / 需求调配业务服务类"""

    def __init__(self):
        self.bottle_service = reagent_bottle_service
        self.order_service = allocation_order_service
        self.order_item_service = allocation_order_item_service
        self.demand_service = reagent_demand_service
        self.demand_item_service = reagent_demand_item_service
        self.person_service = person_service
        self.manager = manager_service
        self.id_gen = id_generator

    # ------------------------------------------------------------------
    # 基础工具
    # ------------------------------------------------------------------

    @staticmethod
    def _num(value) -> float:
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _department_of(self, name: Optional[str]) -> str:
        if not name:
            return ""
        person = self.person_service.get_by_name(name)
        return (getattr(person, "department", None) or "") if person else ""

    @staticmethod
    def _match_reagent(bottle, cas_number: Optional[str], reagent_name: Optional[str]) -> bool:
        if cas_number:
            return getattr(bottle, ReagentBottleField.CAS_NUMBER, None) == cas_number
        if reagent_name:
            return getattr(bottle, ReagentBottleField.REAGENT_NAME, None) == reagent_name
        return False

    def _available_bottles(self, cas_number, reagent_name) -> List:
        """可借且未过期、有剩余量的目标试剂瓶"""
        result = []
        for bottle in self.bottle_service.get_all_parsed():
            if not self._match_reagent(bottle, cas_number, reagent_name):
                continue
            if getattr(bottle, ReagentBottleField.SCRAP_FLAG, None) in ("待报废", "已报废"):
                continue
            if not is_borrowable(getattr(bottle, ReagentBottleField.BORROWABLE_FLAG, None)):
                continue
            if is_expired(getattr(bottle, ReagentBottleField.EXPIRED_FLAG, None)):
                continue
            if self._num(getattr(bottle, ReagentBottleField.REMAINING_QUANTITY, None)) <= 0:
                continue
            result.append(bottle)
        return result

    @staticmethod
    def _bottle_sort_key(bottle):
        expiry = getattr(bottle, "expiry_date", None) or "9999"
        inbound = getattr(bottle, ReagentBottleField.INBOUND_DATE, None) or "9999"
        return (expiry, inbound, str(getattr(bottle, ReagentBottleField.BOTTLE_NUMBER, "")))

    def _priority(self, manager: Optional[str], requester: str, requester_dept: str) -> int:
        if manager and manager == requester:
            return PRIORITY_SELF
        if manager and requester_dept and self._department_of(manager) == requester_dept:
            return PRIORITY_DEPARTMENT
        return PRIORITY_INSTITUTE

    # ------------------------------------------------------------------
    # 智能分配
    # ------------------------------------------------------------------

    @handle_exception(context="智能分配")
    def plan(
        self,
        qty: float,
        requester: str,
        cas_number: Optional[str] = None,
        reagent_name: Optional[str] = None,
    ) -> ServiceResult:
        """对单一试剂做智能分配

        优先级：本人 → 本教研室 → 全院；组内按效期先后（先到期先用）。

        Returns:
            ServiceResult - data 含 groups（按管理人分组）与 shortage（缺口）
        """
        if qty is None or self._num(qty) <= 0:
            return ServiceResult.fail(message="需求量必须大于0", error_code="INVALID_QTY")
        if not requester:
            return ServiceResult.fail(message="需求人不能为空", error_code="EMPTY_REQUESTER")

        qty = self._num(qty)
        bottles = self._available_bottles(cas_number, reagent_name)
        if not bottles:
            return ServiceResult.fail(
                message="未找到可借的该试剂（可能已被借出/耗尽/过期）",
                error_code="NO_AVAILABLE_BOTTLE",
            )

        requester_dept = self._department_of(requester)

        # 按管理人分组（无管理人归属超级管理员）
        default_manager = self.manager.resolve_manager(None) or UNASSIGNED_MANAGER
        groups: Dict[str, List] = {}
        for bottle in bottles:
            mgr = getattr(bottle, ReagentBottleField.MANAGER, None) or default_manager
            groups.setdefault(mgr, []).append(bottle)

        ordered_managers = sorted(
            groups.keys(),
            key=lambda m: (self._priority(m, requester, requester_dept), str(m)),
        )

        need = qty
        plan_groups = []
        for manager in ordered_managers:
            if need <= 1e-9:
                break
            group_bottles = sorted(groups[manager], key=self._bottle_sort_key)
            items = []
            for bottle in group_bottles:
                if need <= 1e-9:
                    break
                remaining = self._num(getattr(bottle, ReagentBottleField.REMAINING_QUANTITY, None))
                take = min(remaining, need)
                if take <= 0:
                    continue
                items.append({
                    "bottle_number": getattr(bottle, ReagentBottleField.BOTTLE_NUMBER, None),
                    "reagent_name": getattr(bottle, ReagentBottleField.REAGENT_NAME, None),
                    "qty": round(take, 6),
                    "remaining": remaining,
                })
                need -= take
            if items:
                plan_groups.append({
                    "manager": manager,
                    "department": ("" if manager == UNASSIGNED_MANAGER else self._department_of(manager)),
                    "priority": self._priority(manager, requester, requester_dept),
                    "items": items,
                    "total_qty": round(sum(i["qty"] for i in items), 6),
                })

        shortage = round(max(0.0, need), 6)
        logger.info(
            "智能分配完成",
            requester=requester,
            requested=qty,
            groups=len(plan_groups),
            shortage=shortage,
        )
        return ServiceResult.ok(
            data={
                "requested_qty": qty,
                "groups": plan_groups,
                "shortage": shortage,
            }
        )

    # ------------------------------------------------------------------
    # 智能计算（本年度需求量 vs 存量）
    # ------------------------------------------------------------------

    @staticmethod
    def _in_current_academic_year(borrow_time: Optional[str]) -> bool:
        """判断时间是否落在当前学年（8月—次年7月）"""
        if not borrow_time:
            return False
        try:
            date_part = str(borrow_time).split(" ")[0]
            y, m = date_part.split("/")[0], date_part.split("/")[1]
            year, month = int(y), int(m)
        except (ValueError, IndexError):
            return False
        now = datetime.now()
        start_year = now.year if now.month >= 8 else now.year - 1
        return (year == start_year and month >= 8) or (year == start_year + 1 and month <= 7)

    def _year_demand(self, cas_number, reagent_name) -> float:
        """本年度（学年）该试剂的需求量合计"""
        demands = {d.id: d for d in self.demand_service.get_all_parsed()}
        total = 0.0
        for item in self.demand_item_service.get_all_parsed():
            if not self._match_reagent(item, cas_number, reagent_name):
                continue
            demand = demands.get(item.demand_id)
            if demand and self._in_current_academic_year(demand.borrow_time):
                total += self._num(item.requested_qty)
        return round(total, 6)

    def _stock(self, cas_number, reagent_name, manager: Optional[str] = None) -> float:
        """可借存量合计（manager 为 None 时统计全院）"""
        total = 0.0
        for bottle in self._available_bottles(cas_number, reagent_name):
            if manager is not None:
                bm = getattr(bottle, ReagentBottleField.MANAGER, None) or UNASSIGNED_MANAGER
                if bm != manager:
                    continue
            total += self._num(getattr(bottle, ReagentBottleField.REMAINING_QUANTITY, None))
        return round(total, 6)

    # ------------------------------------------------------------------
    # 生成调配单
    # ------------------------------------------------------------------

    @handle_exception(context="生成调配单")
    def generate_allocation_orders(
        self,
        demand_id: int,
        requester: str,
        lines: List[Dict[str, Any]],
        created_by: Optional[str] = None,
    ) -> ServiceResult:
        """按需求明细生成调配单（每个管理人一张）

        Args:
            demand_id: 需求单ID
            requester: 需求人
            lines: 明细列表，每项含 reagent_name/cas_number/requested_qty

        Returns:
            ServiceResult - data 为生成的调配单简要列表
        """
        created = []
        shortages = []
        for line in lines:
            cas = line.get("cas_number")
            name = line.get("reagent_name")
            req_qty = self._num(line.get("requested_qty"))
            plan_result = self.plan(req_qty, requester, cas_number=cas, reagent_name=name)
            if plan_result.is_failure():
                shortages.append({"reagent_name": name, "reason": plan_result.message})
                continue

            plan = plan_result.data
            if self._num(plan.get("shortage")) > 0:
                shortages.append({
                    "reagent_name": name,
                    "reason": f"可借不足，缺口 {plan['shortage']}",
                })

            year_demand = self._year_demand(cas, name)
            total_stock = self._stock(cas, name)

            for group in plan["groups"]:
                manager = group["manager"]
                manager_stock = self._stock(cas, name, manager=None if manager == UNASSIGNED_MANAGER else manager)
                sufficient = 1 if total_stock >= year_demand else 0
                alloc_number = self.id_gen.generate_allocation_number()
                alloc_id = self.order_service.create({
                    AllocationOrderField.ALLOCATION_NUMBER: alloc_number,
                    AllocationOrderField.DEMAND_ID: demand_id,
                    AllocationOrderField.MANAGER: manager,
                    AllocationOrderField.STATUS: ALLOC_STATUS_PENDING,
                    AllocationOrderField.DEMAND_QTY: group["total_qty"],
                    AllocationOrderField.MANAGER_STOCK_QTY: manager_stock,
                    AllocationOrderField.TOTAL_STOCK_QTY: total_stock,
                    AllocationOrderField.YEAR_DEMAND_QTY: year_demand,
                    AllocationOrderField.IS_STOCK_SUFFICIENT: sufficient,
                    AllocationOrderField.CREATED_BY: created_by,
                })
                if not alloc_id:
                    logger.error("创建调配单失败", demand_id=demand_id, manager=manager)
                    continue
                for item in group["items"]:
                    self.order_item_service.create({
                        AllocationOrderItemField.ALLOCATION_ID: alloc_id,
                        AllocationOrderItemField.BOTTLE_NUMBER: item["bottle_number"],
                        AllocationOrderItemField.REAGENT_NAME: item["reagent_name"],
                        AllocationOrderItemField.QTY: item["qty"],
                        AllocationOrderItemField.STATUS: ALLOC_ITEM_PENDING,
                    })
                created.append({
                    "allocation_number": alloc_number,
                    "manager": manager,
                    "total_qty": group["total_qty"],
                    "is_stock_sufficient": sufficient,
                })

        if not created:
            return ServiceResult.fail(
                message="未能生成任何调配单（无可借试剂）",
                error_code="NO_ALLOCATION_CREATED",
                data={"shortages": shortages},
            )
        return ServiceResult.ok(
            data={"created": created, "shortages": shortages},
            message=f"已生成 {len(created)} 张调配单",
        )

    # ------------------------------------------------------------------
    # 处理调配单
    # ------------------------------------------------------------------

    def _refresh_demand_status(self, demand_id: int) -> None:
        orders = self.order_service.get_by_demand(demand_id)
        if not orders:
            return
        statuses = {o.status for o in orders}
        if statuses == {ALLOC_STATUS_LENT}:
            new_status = DEMAND_STATUS_DONE
        elif statuses == {ALLOC_STATUS_REJECTED}:
            new_status = DEMAND_STATUS_REJECTED
        elif ALLOC_STATUS_PENDING in statuses:
            new_status = DEMAND_STATUS_PENDING
        else:
            new_status = DEMAND_STATUS_PARTIAL
        self.demand_service.update(demand_id, {ReagentDemandField.STATUS: new_status})

    @handle_exception(context="处理调配单")
    def handle(self, allocation_id: int, decision: str, operator: str) -> ServiceResult:
        """管理员处理调配单：借出 / 退回

        - 借出（lend）：把调配单内试剂的管理权流转到需求人名下（+变更记录）
        - 退回（reject）：驳回该调配单

        Args:
            allocation_id: 调配单ID
            decision: 'lend'（借出）或 'reject'（退回）
            operator: 操作人

        Returns:
            ServiceResult
        """
        if decision not in ("lend", "reject"):
            return ServiceResult.fail(message="无效的决策", error_code="INVALID_DECISION")

        order = self.order_service.get_by_id(allocation_id)
        if not order:
            return ServiceResult.fail(message="未找到该调配单", error_code="ALLOCATION_NOT_FOUND")
        if order.status != ALLOC_STATUS_PENDING:
            return ServiceResult.fail(
                message=f"该调配单已处理（{order.status}）",
                error_code="ALLOCATION_HANDLED",
            )

        items = self.order_item_service.get_by_allocation(allocation_id)
        handled_at = datetime.now().strftime("%Y/%m/%d %H:%M")

        if decision == "reject":
            for item in items:
                self.order_item_service.update(item.id, {AllocationOrderItemField.STATUS: ALLOC_ITEM_REJECTED})
            self.order_service.update(
                allocation_id,
                {
                    AllocationOrderField.STATUS: ALLOC_STATUS_REJECTED,
                    AllocationOrderField.HANDLED_AT: handled_at,
                },
            )
            self._refresh_demand_status(order.demand_id)
            audit(operator, "调配退回", target_type="allocation",
                  target_id=order.allocation_number, detail="管理员退回调配单")
            return ServiceResult.ok(message="已退回该调配单")

        # 借出 = 管理权流转：把试剂管理权转到需求人手里（不同管理员之间流转试剂）
        demand = self.demand_service.get_by_id(order.demand_id)
        new_manager = (demand.requester if demand else "") or order.created_by or operator

        lent_items, failed = [], []
        for item in items:
            bottle = self.bottle_service.get_by_bottle_number(item.bottle_number)
            if not bottle:
                failed.append(f"{item.bottle_number}: 试剂瓶不存在")
                continue
            current = self.manager.resolve_manager(
                getattr(bottle, ReagentBottleField.MANAGER, None)
            )
            if current == new_manager:
                # 已由需求人持有，无需流转
                self.order_item_service.update(
                    item.id, {AllocationOrderItemField.STATUS: ALLOC_ITEM_LENT}
                )
                lent_items.append(item.bottle_number)
                continue
            transfer_result = self.manager.transfer(
                item.bottle_number,
                new_manager,
                operator,
                reason=REASON_ALLOCATION,
                ref_type="allocation",
                ref_id=order.allocation_number,
            )
            if transfer_result.is_success():
                self.order_item_service.update(
                    item.id, {AllocationOrderItemField.STATUS: ALLOC_ITEM_LENT}
                )
                lent_items.append(item.bottle_number)
            else:
                failed.append(f"{item.bottle_number}: {transfer_result.message}")

        if not lent_items:
            return ServiceResult.fail(
                message="借出失败：" + "；".join(failed),
                error_code="LEND_FAILED",
            )

        self.order_service.update(
            allocation_id,
            {
                AllocationOrderField.STATUS: ALLOC_STATUS_LENT,
                AllocationOrderField.HANDLED_AT: handled_at,
            },
        )
        self._refresh_demand_status(order.demand_id)

        audit(operator, "调配借出", target_type="allocation",
              target_id=order.allocation_number,
              detail=f"受理人 {order.manager} 流转给 {new_manager}，{len(lent_items)} 瓶")

        message = f"已借出 {len(lent_items)} 瓶（新管理人：{new_manager}）"
        if failed:
            message += f"；{len(failed)} 瓶失败：{'；'.join(failed)}"
        return ServiceResult.ok(
            data={"lent": lent_items, "failed": failed},
            message=message,
        )


# ============================================================================
# 全局单例实例
# ============================================================================

allocation_service = AllocationService()
