"""两段管线的业务编排。

业务层的职责只有三件：

1. **装配**：把路由表、保管账、物性目录装成一条可执行的管线
2. **落痕迹**：受理结论与调拨建议要留档，事后能查「当时按什么算的」
3. **执行**：调拨建议不会自己生效——动保管权必须走
   :meth:`business.manager_service.ManagerService.transfer`，那里会写
   ``manager_change_log``

计算在这里一行都没有：够不够是 ``SupplyEvaluator`` 的判断，从谁那调是
``TransferBroker`` 的判断。业务层若开始自己算数，两段管线的边界就烂了。

**关于「教师不是保管人」的落点**：本服务从不把教师写进任何 bottles 的
``manager`` 字段。教师领用走的是第一段的 ``IssueLine``（出库），而不是
第二段的 ``TransferLine``（保管权流转）。两条路径在这里分岔，不会串。
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from business.manager_service import REASON_ALLOCATION, manager_service
from capabilities.circulation.ledger import CustodyLedger, EmptyLedger
from capabilities.circulation.picking import ShelfPolicy
from capabilities.circulation.pipeline import MaterialPipeline
from capabilities.circulation.routing import (
    CompositeRouter,
    CustodianRouter,
    DepartmentRouter,
    RoutingError,
    SourceRouter,
    StaticRouter,
)
from capabilities.circulation.stage1 import AcceptanceDesk
from capabilities.circulation.stage2 import TransferBroker
from capabilities.metering import CatalogSubstanceResolver
from capabilities.supply.evaluator import SupplyEvaluator
from domain.custody import Custodian
from domain.pipeline import (
    Acceptance,
    PipelineError,
    PipelineResult,
    TeacherRequest,
    TransferProposal,
)
from domain.batch import BatchScale
from domain.recipe import SourceRef
from domain.requirement import RequirementLine, RequirementSheet
from domain.substance import ComponentRole, SubstanceRef
from domain.units import Quantity
from services.core.requirement_sheet_service import requirement_sheet_service
from services.custodian_route import (
    SCOPE_COURSE,
    SCOPE_DEPARTMENT,
    custodian_route_repository,
)
from services.custody_ledger import custody_ledger_assembler
from services.demand_reserve import demand_reserve
from utils.error_handler import ServiceResult, handle_exception, logger


class MaterialPipelineService:
    """教师申领 → 受理 → 平账 的业务服务。"""

    def __init__(
        self,
        ledger_assembler=None,
        routes=None,
        resolver=None,
        managers=None,
        policy=None,
        reserve=None,
    ) -> None:
        self.ledger_assembler = ledger_assembler or custody_ledger_assembler
        self.routes = routes or custodian_route_repository
        self.resolver = resolver or CatalogSubstanceResolver()
        self.managers = managers or manager_service
        # 抽卡规则与保底来源：两段共用同一份，别在三个地方各建一个默认值
        self.policy = policy or ShelfPolicy()
        # reserve 为 None 表示不保底。页面装配时注入 DemandReserve，
        # 测试默认不注入——保底要查库，会让纯计算的用例变得依赖库状态。
        self.reserve = reserve

    def _evaluator(self) -> SupplyEvaluator:
        return SupplyEvaluator(resolver=self.resolver)

    # ------------------------------------------------------------------
    # 装配
    # ------------------------------------------------------------------
    def ledger(self) -> CustodyLedger:
        try:
            return self.ledger_assembler.build()
        except Exception as exc:  # 库还没建表 / 还没初始化
            logger.warning(f"保管账装配失败，降级为空账: {exc}")
            return EmptyLedger()

    def router(self) -> CustodianRouter:
        """路由优先级：课程指派 → 科室指派 → 超级管理员兜底。

        每一层都是**明确配置**的，不存在"猜一个"。三层都没有时会抛
        :class:`RoutingError`——让老师看见"这门课还没配受理人"，比让系统
        随便找个人受理要好得多。
        """
        department_of = self.ledger_assembler.department_of
        routers: list[CustodianRouter] = []

        course_rules = self.routes.rules(SCOPE_COURSE, department_of)
        if course_rules:
            routers.append(SourceRouter(course_rules, label="按课程指派"))

        department_rules = self.routes.rules(SCOPE_DEPARTMENT, department_of)
        if department_rules:
            routers.append(DepartmentRouter(department_of, department_rules))

        super_admin = self._super_admin()
        if super_admin is not None:
            routers.append(StaticRouter(super_admin))

        if not routers:
            raise RoutingError(
                "还没有配置任何受理人路由：请先在「保管人路由」里指定"
                "课程/科室对应的管理员，或设置一名超级管理员兜底"
            )
        if len(routers) == 1:
            return routers[0]
        return CompositeRouter(*routers)

    def _super_admin(self) -> Optional[Custodian]:
        try:
            name = self.managers.get_super_admin_name()
        except Exception as exc:
            logger.warning(f"读取超级管理员失败: {exc}")
            return None
        if not name:
            return None
        return Custodian(
            name=name,
            department=self.ledger_assembler.department_of(name) or "",
            is_super_admin=True,
        )

    def pipeline(self, ledger: Optional[CustodyLedger] = None) -> MaterialPipeline:
        ledger = ledger or self.ledger()
        return MaterialPipeline(
            self.router(),
            ledger,
            self._evaluator(),
            policy=self.policy,
            reserve=self.reserve,
        )

    # ------------------------------------------------------------------
    # 第一段
    # ------------------------------------------------------------------
    @handle_exception(context="受理教师申领")
    def intake(
        self,
        requester: str,
        sheet: RequirementSheet,
        source: Optional[SourceRef] = None,
        due_hint: str = "",
        note: str = "",
        sheet_number: str = "",
        operator: str = "",
    ) -> ServiceResult:
        """受理一张申请（只走第一段）。

        给出 ``sheet_number`` 时，受理成功就把这张单推到 ``submitted``。
        这一步不能省：``draft`` 是老师自己算着玩的单，不该锁料；受理才是
        承诺——从这一刻起它占保底，也才轮到「逐项兑付」把状态往前推。
        页面生成的需求单落库就是 ``draft``，中间没有别的提交动作，不在这
        里推进的话，保底永远算不到任何一张单。

        Returns:
            ServiceResult，``data`` 含 ``acceptance``（快照）与摘要字段。
        """
        request = TeacherRequest(
            requester=requester,
            sheet=sheet,
            source=source,
            due_hint=due_hint,
            note=note,
        )
        ledger = self.ledger()
        acceptance = AcceptanceDesk(
            self.router(),
            ledger,
            self._evaluator(),
            policy=self.policy,
            reserve=self.reserve,
        ).receive(request)
        if sheet_number:
            # 只在草稿上推进。已经 submitted/partial/issued 的单不能被打回，
            # 否则第二次受理会把兑付进度踩平——保底又会把发出去的料算成欠量。
            requirement_sheet_service.promote_to_submitted(
                sheet_number, operator or requester
            )
        return ServiceResult.ok(
            data=self._acceptance_payload(acceptance), message=acceptance.describe()
        )

    # ------------------------------------------------------------------
    # 第二段
    # ------------------------------------------------------------------
    @handle_exception(context="平账调拨")
    def settle(self, acceptance: Acceptance) -> ServiceResult:
        """对已受理的申请做平账（只走第二段）。

        刻意不重算第一段：重算会用到变了之后的库存，结论可能与当初承诺
        的不一致，事后对不上账。
        """
        ledger = self.ledger()
        proposal = TransferBroker(
            ledger,
            self._evaluator(),
            policy=self.policy,
            reserve=self.reserve,
        ).broker(acceptance)
        result = PipelineResult(
            request=acceptance.request,
            acceptance=acceptance,
            proposal=proposal,
            trace=tuple(acceptance.explain() + proposal.explain()),
        )
        return ServiceResult.ok(data=self._pipeline_payload(result), message=result.describe())

    # ------------------------------------------------------------------
    # 一条龙
    # ------------------------------------------------------------------
    @handle_exception(context="申领走完整管线")
    def run(
        self,
        requester: str,
        sheet: RequirementSheet,
        source: Optional[SourceRef] = None,
        due_hint: str = "",
    ) -> ServiceResult:
        request = TeacherRequest(
            requester=requester, sheet=sheet, source=source, due_hint=due_hint
        )
        result = self.pipeline().run(request)
        return ServiceResult.ok(data=self._pipeline_payload(result), message=result.describe())

    # ------------------------------------------------------------------
    # 执行：把调拨建议变成真实的保管权流转
    # ------------------------------------------------------------------
    @handle_exception(context="执行调拨")
    def commit_transfers(
        self, proposal: TransferProposal, operator: str, note: str = ""
    ) -> ServiceResult:
        """按建议逐瓶转保管权。

        只处理能精确到瓶的行。跨量纲那类（只知道"折合 40 mL"、不知道是哪
        一瓶）不猜——交给现场人工办理，并如实报告，而不是随便挑一瓶把账
        改掉。
        """
        if proposal.is_empty:
            return ServiceResult.ok(message="没有需要执行的调拨")

        transferred: list[dict] = []
        skipped: list[dict] = []
        failed: list[dict] = []

        for line in proposal.lines:
            lots = self._split_lots(line.lot_id)
            if not lots:
                skipped.append(
                    {
                        "substance": line.name,
                        "quantity": line.quantity.format(3),
                        "reason": "未指定具体瓶（跨量纲或需现场取），请人工办理",
                    }
                )
                continue
            for lot_id in lots:
                result = self.managers.transfer(
                    lot_id,
                    line.to_custodian.name,
                    operator,
                    reason=REASON_ALLOCATION,
                    ref_type="pipeline",
                    ref_id=note or datetime.now().strftime("PIPE%Y%m%d%H%M%S"),
                )
                if result.is_success():
                    transferred.append(
                        {
                            "lot_id": lot_id,
                            "from": line.from_custodian.name,
                            "to": line.to_custodian.name,
                            "substance": line.name,
                        }
                    )
                else:
                    failed.append({"lot_id": lot_id, "reason": result.message})

        parts = [f"已流转 {len(transferred)} 瓶保管权"]
        if skipped:
            parts.append(f"{len(skipped)} 项需人工办理")
        if failed:
            parts.append(f"{len(failed)} 瓶失败")
        data = {"transferred": transferred, "skipped": skipped, "failed": failed}
        message = "；".join(parts)
        if failed and not transferred:
            return ServiceResult.fail(message=message, error_code="TRANSFER_FAILED", data=data)
        return ServiceResult.ok(data=data, message=message)

    @staticmethod
    def _split_lots(lot_id: str) -> tuple[str, ...]:
        """``"B-01,B-02"`` → ``("B-01", "B-02")``；空串 → 空元组。"""
        if not lot_id:
            return ()
        return tuple(
            part.strip() for part in str(lot_id).split(",") if part.strip()
        )

    # ------------------------------------------------------------------
    # 摘要
    # ------------------------------------------------------------------
    @handle_exception(context="保管账摘要")
    def custody_summary(self) -> ServiceResult:
        """保管账摘要（页面顶部与"该找谁"提示用）。"""
        ledger = self.ledger()
        data = ledger.holdings().to_rows()
        try:
            router_desc = self.router().describe()
        except RoutingError as exc:
            router_desc = f"尚未配置：{exc}"
        return ServiceResult.ok(
            data={
                "rows": data,
                "ledger_text": ledger.describe(),
                "router_text": router_desc,
                "custodians": [c.describe() for c in ledger.custodians()],
                "unclaimed": sorted(
                    {lot.substance.name or lot.substance.key for lot in ledger.unclaimed()}
                ),
            }
        )

    @handle_exception(context="查询受理人")
    def custodian_for(
        self, source: Optional[SourceRef], requester: str = "", title: str = ""
    ) -> ServiceResult:
        """这门课该找谁（页面在提交前先告诉老师）。

        用一张一行假单去问路由，只为借它的匹配逻辑——路由只看 ``source``
        与申请人科室，不看料。这样页面不必先算完整需求就能提示受理人。
        """
        probe = RequirementSheet(
            recipe_key="_probe",
            title=title or "受理人探测",
            scale=BatchScale.single(),
            lines=(
                RequirementLine(
                    substance=SubstanceRef.of("探测物质"),
                    role=ComponentRole.REAGENT,
                    quantity=Quantity.of(1, "g"),
                ),
            ),
        )
        try:
            request = TeacherRequest(
                requester=requester or "（待定）", sheet=probe, source=source
            )
            custodian = self.router().route(request)
        except RoutingError as exc:
            return ServiceResult.fail(message=str(exc), error_code="NO_CUSTODIAN")
        return ServiceResult.ok(
            data={
                "custodian": custodian.name,
                "department": custodian.department,
                "is_super_admin": custodian.is_super_admin,
                "text": f"本次申请由 {custodian.describe()} 受理",
            },
            message=f"受理人：{custodian.describe()}",
        )

    # ------------------------------------------------------------------
    # 内部：载荷
    # ------------------------------------------------------------------
    @staticmethod
    def _acceptance_payload(acceptance: Acceptance) -> dict:
        return {
            "acceptance": acceptance,
            "custodian": acceptance.custodian.name,
            "custodian_department": acceptance.custodian.department,
            "requester": acceptance.request.requester_name,
            "title": acceptance.request.sheet.title,
            "issued": [line.to_record() for line in acceptance.issued],
            "shortfalls": [item.to_record() if hasattr(item, "to_record") else {
                "substance_key": item.substance.key,
                "display_name": item.name,
                "quantity": item.quantity.to_float(),
                "unit": item.quantity.unit.symbol,
                "reason": item.reason,
            } for item in acceptance.shortfalls],
            "is_complete": acceptance.is_complete,
            "needs_rebalance": not acceptance.is_complete,
            "notes": list(acceptance.notes),
            "text": acceptance.describe(),
        }

    @staticmethod
    def _pipeline_payload(result: PipelineResult) -> dict:
        return {
            "result": result,
            "acceptance": result.acceptance,
            "proposal": result.proposal,
            "custodian": result.custodian.name,
            "trace": list(result.trace),
            "is_fulfilled": result.is_fulfilled,
            "needs_purchase": result.needs_purchase,
            "purchase_sheet": result.purchase_sheet,
            "text": result.describe(),
        }


material_pipeline_service = MaterialPipelineService(reserve=demand_reserve)


__all__ = ["MaterialPipelineService", "material_pipeline_service"]
