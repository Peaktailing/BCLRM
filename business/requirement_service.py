"""需求计划业务服务：把「配方 + 规模」走成一条可执行、可追溯的链路。

这是两条纵线真正咬合的地方，一条用例串起四件事：

1. **算**：配方 × 规模 → 需求单（计量中台）
2. **对账**：需求 vs 库存可用量 → 缺口（供应中台）
3. **补货**：缺口 → 采购建议（供应中台）
4. **落地**：需求单 → 领用单据（流转中台）

业务层只做编排与决策，任何一步的算法都在中台里，改算法不动用例。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from capabilities.circulation import (
    CirculationError,
    CirculationGateway,
    DemandTicket,
    GatewayNotReady,
    InMemoryCirculationGateway,
)
from capabilities.metering import MeteringEngine, MeteringError
from capabilities.supply import (
    ProcurementPlanner,
    PurchaseProposal,
    StockSnapshot,
    SupplyAssessment,
    SupplyEvaluator,
    StaticPackCatalog,
    standard_policy,
    strict_policy,
)
from domain.batch import BatchScale, scale_of
from domain.recipe import Recipe
from domain.requirement import CoverageReport, RequirementSheet
from utils.audit import audit
from utils.error_handler import ServiceResult, handle_exception, logger
from utils.permission_guard import enforce_role

#: 可发起领用申请的角色（学生 user 也可发起，审批在网关侧控制）
REQUEST_ROLES = ("user", "teacher", "admin", "super_admin")


class RequirementBusinessService:
    """需求计划用例服务。"""

    def __init__(
        self,
        recipes=None,
        metering: Optional[MeteringEngine] = None,
        resolver=None,
        gateway: Optional[CirculationGateway] = None,
        planner: Optional[ProcurementPlanner] = None,
        sheets=None,
        stock_provider=None,
    ) -> None:
        self._recipes = recipes
        self._metering = metering
        self._resolver = resolver
        self._gateway = gateway
        self._planner = planner
        self._sheets = sheets
        self._stock_provider = stock_provider

    # ---------------------------------------------------------------- 依赖
    @property
    def recipes(self):
        if self._recipes is None:
            from business.recipe_service import recipe_business_service
            self._recipes = recipe_business_service
        return self._recipes

    @property
    def resolver(self):
        if self._resolver is None:
            from services.substance_catalog import build_resolver
            self._resolver = build_resolver()
        return self._resolver

    @property
    def metering(self) -> MeteringEngine:
        if self._metering is None:
            self._metering = MeteringEngine(self.resolver)
        return self._metering

    @property
    def gateway(self) -> CirculationGateway:
        """默认内存网关：在接通 BCLRM 三层单据前，它能完整跑通流程。"""
        if self._gateway is None:
            self._gateway = InMemoryCirculationGateway()
        return self._gateway

    @property
    def planner(self) -> ProcurementPlanner:
        if self._planner is None:
            # 还没有包装规格目录时，规划器仍会给出「按缺口询价」的行
            self._planner = ProcurementPlanner(StaticPackCatalog())
        return self._planner

    @property
    def sheets(self):
        if self._sheets is None:
            from services.recipe_repository import SqliteRequirementRepository
            self._sheets = SqliteRequirementRepository()
        return self._sheets

    @property
    def stock_provider(self):
        if self._stock_provider is None:
            from services.stock_snapshot import BottleStockProvider
            self._stock_provider = BottleStockProvider()
        return self._stock_provider

    # ---------------------------------------------------------------- 试算
    @handle_exception(context="试算物料需求")
    def preview(
        self,
        recipe_key: str,
        scale: Any = None,
        policy_name: str = "standard",
        include_proposal: bool = True,
    ) -> ServiceResult:
        """只算不落库：算出需求、可用量、缺口与采购建议。"""
        recipe = self._load_recipe(recipe_key)
        if recipe is None:
            return ServiceResult.fail(
                message=f"配方不存在：{recipe_key}", error_code="RECIPE_NOT_FOUND"
            )

        prepared = self._prepare(recipe, scale, policy_name)
        if not prepared.success:
            return prepared

        payload = prepared.data
        data = self._plan_dto(
            payload["recipe"],
            payload["metering"].sheet,
            payload["assessment"],
            payload["proposal"] if include_proposal else None,
            payload["metering"].explain(),
        )
        return ServiceResult.ok(data=data, message=data["summary"])

    # ---------------------------------------------------------------- 落库
    @handle_exception(context="生成需求单")
    def create_sheet(
        self,
        recipe_key: str,
        scale: Any = None,
        requester: str = "",
        policy_name: str = "standard",
        submit: bool = False,
        note: str = "",
    ) -> ServiceResult:
        """算 + 对账 + 落库（可选同时提交领用申请）。"""
        enforce_role(*REQUEST_ROLES, action="生成需求单")

        recipe = self._load_recipe(recipe_key)
        if recipe is None:
            return ServiceResult.fail(
                message=f"配方不存在：{recipe_key}", error_code="RECIPE_NOT_FOUND"
            )

        prepared = self._prepare(recipe, scale, policy_name)
        if not prepared.success:
            return prepared

        payload = prepared.data
        sheet: RequirementSheet = payload["metering"].sheet
        assessment: SupplyAssessment = payload["assessment"]

        snapshot_data = {
            line.requirement.key: {
                "available": line.available.to_float(),
                "gap": line.gap.to_float(),
                "coverage": float(line.coverage_ratio),
            }
            for line in assessment.coverage.lines
        }

        sheet_number = self.sheets.save(sheet, requester or "未署名", snapshot_data)

        # 落归属（指定人 → 教研室池 → 全院池）。失败不阻断建单：归属为空的
        # 单在业务上按 all 处理，退化成升级前的行为，比「算出了单却存不进去」
        # 要好。这一步必须在落库之后——它要读回 requester/source_code。
        try:
            from business.assignment_service import assignment_service

            assignment_service.assign_for_sheet(sheet_number)
        except Exception as exc:
            logger.warning(f"需求单 {sheet_number} 归属计算失败，按全院池处理: {exc}")

        audit(
            requester,
            "生成需求单",
            "requirement_sheet",
            sheet_number,
            f"{sheet.title}·{sheet.scale.describe()}·{len(sheet.lines)} 项·"
            f"{len(assessment.shortages)} 项缺口",
        )

        ticket = None
        submit_error = ""
        if submit:
            try:
                ticket = self.gateway.submit(sheet, requester or "未署名", note)
            except (GatewayNotReady, CirculationError) as exc:
                # 单已经落库，提交失败不能回滚整件事——如实报告「已生成未提交」
                submit_error = str(exc)
                logger.warning(f"需求单 {sheet_number} 已生成但未能提交: {exc}")

        data = self._plan_dto(
            recipe, sheet, assessment, payload["proposal"], payload["metering"].explain()
        )
        data["sheet_number"] = sheet_number
        data["ticket"] = self._ticket_dto(ticket) if ticket else None
        message = f"已生成需求单 {sheet_number}，{assessment.coverage.summary()}"
        if ticket:
            message += f"；已提交领用申请 {ticket.ticket_no}（{ticket.status.label}）"
        elif submit_error:
            message += f"；但未能进入流转：{submit_error}"
        data["submit_error"] = submit_error
        return ServiceResult.ok(data=data, message=message)

    # ---------------------------------------------------------------- 单据
    @handle_exception(context="提交领用申请")
    def submit_sheet(self, sheet_number: str, requester: str = "", approver: str = "") -> ServiceResult:
        """把已落库的需求单提交为领用单据。"""
        sheet = self.sheets.get(sheet_number)
        if sheet is None:
            return ServiceResult.fail(
                message=f"需求单不存在：{sheet_number}", error_code="SHEET_NOT_FOUND"
            )
        ticket = self.gateway.submit(sheet, requester or "未署名", "")
        self.sheets.set_status(sheet_number, "submitted", approver)
        audit(approver, "提交领用申请", "requirement_sheet", sheet_number, ticket.ticket_no)
        return ServiceResult.ok(
            data={"ticket": self._ticket_dto(ticket)},
            message=f"已提交 {ticket.ticket_no}，当前状态：{ticket.status.label}",
        )

    @handle_exception(context="审批领用申请")
    def approve_ticket(self, ticket_no: str, approver: str, note: str = "") -> ServiceResult:
        try:
            ticket = self.gateway.approve(ticket_no, approver, note)
        except GatewayNotReady as exc:
            return ServiceResult.fail(message=str(exc), error_code="GATEWAY_NOT_READY")
        except CirculationError as exc:
            return ServiceResult.fail(message=str(exc), error_code="CIRCULATION_DENIED")
        audit(approver, "审批通过", "demand_ticket", ticket_no, ticket.sheet.title)
        return ServiceResult.ok(
            data={"ticket": self._ticket_dto(ticket)}, message=f"{ticket_no} 已批准"
        )

    @handle_exception(context="发放领用申请")
    def issue_ticket(self, ticket_no: str, operator: str, note: str = "") -> ServiceResult:
        try:
            ticket = self.gateway.issue(ticket_no, operator, note)
        except GatewayNotReady as exc:
            return ServiceResult.fail(message=str(exc), error_code="GATEWAY_NOT_READY")
        except CirculationError as exc:
            return ServiceResult.fail(message=str(exc), error_code="CIRCULATION_DENIED")
        audit(operator, "发放试剂", "demand_ticket", ticket_no, ticket.sheet.title)
        return ServiceResult.ok(
            data={"ticket": self._ticket_dto(ticket)}, message=f"{ticket_no} 已发放"
        )

    @handle_exception(context="查询未完结单据")
    def open_tickets(self) -> ServiceResult:
        tickets = self.gateway.open_tickets()
        return ServiceResult.ok(
            data={"items": [self._ticket_dto(t) for t in tickets], "total": len(tickets)},
            message=f"{len(tickets)} 张未完结单据",
        )

    # ---------------------------------------------------------------- 查询
    @handle_exception(context="读取需求单")
    def get_sheet(self, sheet_number: str) -> ServiceResult:
        sheet = self.sheets.get(sheet_number)
        if sheet is None:
            return ServiceResult.fail(
                message=f"需求单不存在：{sheet_number}", error_code="SHEET_NOT_FOUND"
            )
        return ServiceResult.ok(
            data={
                "sheet": sheet,
                "sheet_number": sheet_number,
                "lines": [
                    {
                        "seq": line.seq,
                        "name": line.name,
                        "quantity": line.quantity.format(3),
                        "unit": line.quantity.unit.symbol,
                        "basis": line.basis_text,
                        "explanation": line.explanation,
                        "controlled": line.controlled,
                    }
                    for line in sheet.lines
                ],
                "summary": sheet.describe(),
            },
            message=sheet.describe(),
        )

    @handle_exception(context="查询需求单列表")
    def recent_sheets(self, limit: int = 50) -> ServiceResult:
        rows = self.sheets.list_recent(limit)
        return ServiceResult.ok(data={"items": rows, "total": len(rows)}, message=f"{len(rows)} 张需求单")

    # ---------------------------------------------------------------- 内部
    def _load_recipe(self, recipe_key: str) -> Optional[Recipe]:
        result = self.recipes.get_recipe(recipe_key)
        if not result.success:
            return None
        return result.data["recipe"]

    def _prepare(self, recipe: Recipe, scale: Any, policy_name: str) -> ServiceResult:
        """算 + 对账 + 采购建议（预览与落库共用）。"""
        batch_scale = self._scale(scale) or BatchScale.single()
        policy = strict_policy() if policy_name == "strict" else standard_policy()

        try:
            metering = self.metering.plan(
                recipe, batch_scale, controlled_keys=self._controlled_keys()
            )
        except MeteringError as exc:
            return ServiceResult.fail(message=f"无法计算需求：{exc}", error_code="METERING_FAILED")

        snapshot = self.stock_provider.snapshot(label=f"配方 {recipe.key}")
        evaluator = SupplyEvaluator(policy, self.resolver)
        assessment = evaluator.assess(metering.sheet, snapshot)
        proposal = self.planner.plan(assessment.coverage)

        return ServiceResult.ok(
            data={
                "recipe": recipe,
                "metering": metering,
                "assessment": assessment,
                "proposal": proposal,
                "snapshot": snapshot,
            }
        )

    @staticmethod
    def _scale(scale: Any) -> Optional[BatchScale]:
        if scale is None:
            return None
        try:
            return scale_of(scale)
        except (TypeError, ValueError):
            return None

    def _controlled_keys(self) -> set[str]:
        """受管控物质引用键（来自管控名录）。读失败不影响计算。"""
        try:
            from services.base.controlled_list_service import controlled_list_service

            rows = controlled_list_service.get_all()
        except Exception as exc:  # 名录读不到不该让整张单算不出来
            logger.warning(f"管控名录读取失败，本次不做管控标记: {exc}")
            return set()

        keys: set[str] = set()
        for row in rows:
            name = (row.get("chemical_name") or "").strip()
            cas = (row.get("cas_number") or "").strip() or None
            alias = (row.get("alias") or "").strip()
            if name or cas:
                from domain.substance import SubstanceRef as _Ref

                keys.add(_Ref.of(name, cas).key)
            if alias:
                from domain.substance import SubstanceRef as _Ref

                keys.add(_Ref.of(alias).key)
        return keys

    # ---------------------------------------------------------------- DTO
    @staticmethod
    def _plan_dto(
        recipe: Recipe,
        sheet: RequirementSheet,
        assessment: SupplyAssessment,
        proposal: Optional[PurchaseProposal],
        explain: List[str],
    ) -> Dict[str, Any]:
        coverage_by_key = {line.requirement.key: line for line in assessment.coverage.lines}
        lines = []
        for line in sheet.lines:
            covered = coverage_by_key.get(line.key)
            lines.append(
                {
                    "seq": line.seq,
                    "name": line.name,
                    "cas": line.substance.cas.value if line.substance.cas else "",
                    "role": line.role.value,
                    "role_label": line.role.label,
                    "quantity": line.quantity.format(3),
                    "unit": line.quantity.unit.symbol,
                    "quantity_value": line.quantity.to_float(),
                    "basis": line.basis_text,
                    "explanation": line.explanation,
                    "controlled": line.controlled,
                    "required": covered.required.format(3) if covered else "",
                    "available": covered.available.format(3) if covered else "",
                    "gap": covered.gap.format(3) if covered else "",
                    "coverage_ratio": float(covered.coverage_ratio) if covered else 1.0,
                    "is_covered": covered.is_covered if covered else True,
                }
            )

        proposal_rows = []
        if proposal is not None:
            proposal_rows = [
                {
                    "name": item.name,
                    "gap": item.gap.format(3),
                    "packs": item.packs,
                    "pack_size": item.pack.pack_size.format(2) if item.pack else "",
                    "supplier": item.pack.supplier if item.pack else "",
                    "cost": float(item.estimated_cost) if item.estimated_cost is not None else None,
                    "note": item.note,
                }
                for item in proposal.lines
            ]

        return {
            "recipe_key": recipe.key,
            "title": recipe.title,
            "scale": sheet.scale.describe(),
            "persons": sheet.scale.persons,
            "batches": sheet.scale.batches,
            "lines": lines,
            "coverage_summary": assessment.coverage.summary(),
            "is_fulfillable": assessment.is_fulfillable,
            "coverage_ratio": float(assessment.coverage.ratio),
            "shortages": [
                {
                    "name": line.requirement.name,
                    "required": line.required.format(3),
                    "available": line.available.format(3),
                    "gap": line.gap.format(3),
                }
                for line in assessment.shortages
            ],
            "proposal": proposal_rows,
            "proposal_summary": proposal.summary() if proposal else "",
            "estimated_cost": float(proposal.estimated_cost) if proposal else 0.0,
            "warnings": list(sheet.warnings),
            "explain": explain,
            "summary": f"{sheet.describe()}；{assessment.coverage.summary()}",
        }

    @staticmethod
    def _ticket_dto(ticket: DemandTicket) -> Dict[str, Any]:
        return {
            "ticket_no": ticket.ticket_no,
            "title": ticket.sheet.title,
            "requester": ticket.requester,
            "status": ticket.status.value,
            "status_label": ticket.status.label,
            "line_count": ticket.line_count,
            "created_at": ticket.created_at.strftime("%Y-%m-%d %H:%M"),
            "events": [event.describe() for event in ticket.events],
        }


# 模块级单例
requirement_business_service = RequirementBusinessService()

__all__ = ["RequirementBusinessService", "requirement_business_service", "REQUEST_ROLES"]
