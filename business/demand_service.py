"""需求调配业务服务

领用入口：需求人提交「需求单」，系统智能分配后按管理人拆分为若干「调配单」，
发到对应管理员手上，由管理员决定借出 / 退回。
"""
from datetime import datetime
from typing import List, Optional, Dict, Any

from services.core.reagent_demand_service import (
    reagent_demand_service,
    reagent_demand_item_service,
)
from services.core.allocation_order_service import (
    allocation_order_service,
    allocation_order_item_service,
)
from business.allocation_service import allocation_service
from business.permission_service import permission_service
from models.core.reagent_demand import (
    DEMAND_STATUS_PENDING,
    DEMAND_STATUS_CANCELLED,
)
from models.core.allocation_order import (
    ALLOC_STATUS_PENDING,
    ALLOC_STATUS_LENT,
    ALLOC_STATUS_REJECTED,
    ALLOC_ITEM_REJECTED,
)
from utils.field_mapper import (
    ReagentDemandField,
    ReagentDemandItemField,
    AllocationOrderField,
    AllocationOrderItemField,
)
from utils.id_generator import id_generator
from utils.error_handler import logger, ServiceResult, handle_exception
from utils.audit import audit


class DemandService:
    """需求调配业务服务类"""

    def __init__(self):
        self.demand_service = reagent_demand_service
        self.demand_item_service = reagent_demand_item_service
        self.order_service = allocation_order_service
        self.order_item_service = allocation_order_item_service
        self.allocation = allocation_service
        self.id_gen = id_generator

    @handle_exception(context="提交需求单")
    def create_demand(
        self,
        requester: str,
        lines: List[Dict[str, Any]],
        order_type: str = "零星领用",
        course_id: Optional[int] = None,
        item_id: Optional[int] = None,
        project_id: Optional[int] = None,
        course_name: Optional[str] = None,
        item_name: Optional[str] = None,
        remark: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> ServiceResult:
        """提交需求单并生成调配单

        Args:
            requester: 需求人（领用人）
            lines: 需求明细列表，每项含 reagent_name / cas_number / requested_qty
            order_type: 零星领用 / 课程领用
            course_id / item_id / project_id: 关联课程、实验、项目（可选）
            course_name / item_name: 名称快照
            remark: 备注
            created_by: 创建人

        Returns:
            ServiceResult - data 含 demand_id / demand_number / allocations
        """
        if not requester or not str(requester).strip():
            return ServiceResult.fail(message="需求人不能为空", error_code="EMPTY_REQUESTER")

        requester = str(requester).strip()
        # 需求调配用于「管理员之间流转试剂」，需求人必须是管理员及以上
        if not permission_service.check_permission(requester, "admin").data:
            return ServiceResult.fail(
                message="需求人必须是管理员及以上（需求调配用于管理员之间流转试剂）",
                error_code="REQUESTER_NOT_ADMIN",
            )

        valid_lines = []
        for line in (lines or []):
            name = (line.get("reagent_name") or "").strip()
            qty = line.get("requested_qty")
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                qty = 0.0
            if name and qty > 0:
                valid_lines.append({
                    "reagent_name": name,
                    "cas_number": line.get("cas_number"),
                    "requested_qty": qty,
                })
        if not valid_lines:
            return ServiceResult.fail(
                message="请至少填写一条有效的试剂需求（名称与数量）",
                error_code="EMPTY_DEMAND_LINES",
            )

        requester = str(requester).strip()
        borrow_time = datetime.now().strftime("%Y/%m/%d %H:%M")
        demand_number = self.id_gen.generate_demand_number()

        demand_id = self.demand_service.create({
            ReagentDemandField.DEMAND_NUMBER: demand_number,
            ReagentDemandField.REQUESTER: requester,
            ReagentDemandField.ORDER_TYPE: order_type,
            ReagentDemandField.COURSE_ID: course_id,
            ReagentDemandField.ITEM_ID: item_id,
            ReagentDemandField.PROJECT_ID: project_id,
            ReagentDemandField.COURSE_NAME: course_name,
            ReagentDemandField.ITEM_NAME: item_name,
            ReagentDemandField.BORROW_TIME: borrow_time,
            ReagentDemandField.STATUS: DEMAND_STATUS_PENDING,
            ReagentDemandField.REMARK: remark,
            ReagentDemandField.CREATED_BY: created_by,
        })
        if not demand_id:
            return ServiceResult.fail(message="创建需求单失败", error_code="DEMAND_CREATE_FAILED")

        for line in valid_lines:
            self.demand_item_service.create({
                ReagentDemandItemField.DEMAND_ID: demand_id,
                ReagentDemandItemField.REAGENT_NAME: line["reagent_name"],
                ReagentDemandItemField.CAS_NUMBER: line["cas_number"],
                ReagentDemandItemField.REQUESTED_QTY: line["requested_qty"],
            })

        alloc_result = self.allocation.generate_allocation_orders(
            demand_id, requester, valid_lines, created_by
        )

        audit(
            created_by or requester,
            "提交需求",
            target_type="demand",
            target_id=demand_number,
            detail=f"需求人 {requester}，{len(valid_lines)} 项试剂",
        )

        data = {
            "demand_id": demand_id,
            "demand_number": demand_number,
            "allocations": alloc_result.data.get("created", []) if alloc_result.is_success() else [],
            "shortages": alloc_result.data.get("shortages", []) if alloc_result.is_success() else [],
        }
        if alloc_result.is_failure():
            return ServiceResult.ok(
                data=data,
                message=f"需求单 {demand_number} 已提交，但{alloc_result.message}",
            )
        return ServiceResult.ok(
            data=data,
            message=f"需求单 {demand_number} 已提交，{alloc_result.message}",
        )

    @handle_exception(context="查询我的需求单")
    def list_by_requester(self, requester: str) -> ServiceResult:
        if not requester:
            return ServiceResult.fail(message="需求人不能为空", error_code="EMPTY_REQUESTER")
        demands = self.demand_service.get_by_requester(requester)
        return ServiceResult.ok(data=demands, message=f"共 {len(demands)} 条需求单")

    @handle_exception(context="查询我的调配单")
    def list_pending_by_manager(self, manager: str) -> ServiceResult:
        """查询待某管理人处理的调配单"""
        if not manager:
            return ServiceResult.fail(message="管理人不能为空", error_code="EMPTY_MANAGER")
        orders = self.order_service.get_pending_by_manager(manager)
        return ServiceResult.ok(data=orders, message=f"待处理 {len(orders)} 张调配单")

    @handle_exception(context="查询调配单明细")
    def get_allocation_items(self, allocation_id: int) -> ServiceResult:
        items = self.order_item_service.get_by_allocation(allocation_id)
        return ServiceResult.ok(data=items)


    @handle_exception(context="撤销需求单")
    def cancel_demand(self, demand_id: int, operator: str) -> ServiceResult:
        """撤销需求单

        仅当该需求单**没有任何已借出**的调配单时可撤销：
        - 未处理的调配单一并置为「已退回」，明细同步退回；
        - 需求单状态置为「已撤销」。

        用于需求提交后无可借试剂（未生成调配单）或等待受理期间撤回。
        """
        demand = self.demand_service.get_by_id(demand_id)
        if not demand:
            return ServiceResult.fail(message="需求单不存在", error_code="DEMAND_NOT_FOUND")

        orders = self.order_service.get_by_demand(demand_id)
        if any((o.status or "") == ALLOC_STATUS_LENT for o in orders):
            return ServiceResult.fail(
                message="该需求单已有调配单借出，不能撤销",
                error_code="DEMAND_ALREADY_LENT",
            )

        handled_at = datetime.now().strftime("%Y/%m/%d %H:%M")
        for order in orders:
            if (order.status or "") != ALLOC_STATUS_PENDING:
                continue
            for item in self.order_item_service.get_by_allocation(order.id):
                self.order_item_service.update(
                    item.id, {AllocationOrderItemField.STATUS: ALLOC_ITEM_REJECTED}
                )
            self.order_service.update(
                order.id,
                {
                    AllocationOrderField.STATUS: ALLOC_STATUS_REJECTED,
                    AllocationOrderField.HANDLED_AT: handled_at,
                },
            )

        self.demand_service.update(
            demand_id, {ReagentDemandField.STATUS: DEMAND_STATUS_CANCELLED}
        )
        audit(
            operator, "撤销需求",
            target_type="demand", target_id=demand.demand_number,
            detail=f"退回 {len(orders)} 张未处理调配单",
        )
        logger.info("需求单已撤销", demand_number=demand.demand_number)
        return ServiceResult.ok(
            message=f"需求单 {demand.demand_number} 已撤销，相关未处理调配单已退回"
        )


# ============================================================================
# 全局单例实例
# ============================================================================

demand_service = DemandService()
