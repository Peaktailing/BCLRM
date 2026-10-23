"""两段管线的装配。

这里只做一件事：把第一段和第二段按**唯一的合法顺序**串起来。

    受理（只报自己名下） → 缺口 → 平账（调别人的）

不允许的调用方式，在这里物理上也不存在：

- 不能跳过受理直接平账：第二段的输入类型是 :class:`Acceptance`，而
  ``Acceptance`` 只能由受理台产出
- 不能把平账结果塞回受理：``Acceptance`` 是不可变的，且 ``broker`` 只读它
- 不能让第二段调受理人自己的料：``TransferBroker`` 内部排除
  ``beneficiary``

这种「用类型把流程钉死」的做法，比在业务层写 if 判断靠谱得多——流程
一旦能靠写错代码绕过，它迟早会被绕过。
"""
from __future__ import annotations

from typing import Optional

from capabilities.circulation.ledger import CustodyLedger
from capabilities.circulation.picking import ReservePort, ShelfPolicy
from capabilities.circulation.routing import CustodianRouter
from capabilities.circulation.stage1 import AcceptanceDesk
from capabilities.circulation.stage2 import TransferBroker
from capabilities.supply.evaluator import SupplyEvaluator
from domain.pipeline import Acceptance, PipelineResult, TeacherRequest, TransferProposal


class MaterialPipeline:
    """教师申领 → 受理 → 平账 的完整管线。"""

    def __init__(
        self,
        router: CustodianRouter,
        ledger: CustodyLedger,
        evaluator: Optional[SupplyEvaluator] = None,
        prefer_same_department: bool = True,
        policy: Optional[ShelfPolicy] = None,
        reserve: Optional[ReservePort] = None,
    ) -> None:
        self.router = router
        self.ledger = ledger
        self.evaluator = evaluator or SupplyEvaluator()
        # 两段共用同一套抽卡规则与同一个保底来源。各建各的会出现这种
        # 情况：第一段按「已开封优先」抽了 A 瓶，第二段建议补料时又按
        # 「先到期先出」抽 B 瓶，同一张单前后指向两个不同的瓶。
        self.policy = policy or ShelfPolicy()
        self.desk = AcceptanceDesk(
            router, ledger, self.evaluator, policy=self.policy, reserve=reserve
        )
        self.broker = TransferBroker(
            ledger,
            self.evaluator,
            prefer_same_department=prefer_same_department,
            policy=self.policy,
            reserve=reserve,
        )

    # ---------------------------------------------------------------- 整条
    def run(self, request: TeacherRequest) -> PipelineResult:
        """一次走完两段。"""
        acceptance = self.receive(request)
        return self.settle(acceptance, request=request)

    def receive(self, request: TeacherRequest) -> Acceptance:
        """只走第一段（管理员看自己的受理结论时用）。"""
        return self.desk.receive(request)

    def settle(
        self,
        acceptance: Acceptance,
        request: Optional[TeacherRequest] = None,
    ) -> PipelineResult:
        """只走第二段。

        已经被受理的申请，管理员点「去调货」时走这里——不必重算第一段
        （重算会用到变了之后的库存，结论可能与当初承诺的不一致）。
        """
        proposal: Optional[TransferProposal] = None
        if not acceptance.is_complete:
            proposal = self.broker.broker(acceptance)

        trace = tuple(acceptance.explain() + (proposal.explain() if proposal else ()))
        return PipelineResult(
            request=request or acceptance.request,
            acceptance=acceptance,
            proposal=proposal,
            trace=trace,
        )

    # ---------------------------------------------------------------- 说明
    def describe(self) -> str:
        parts = [
            f"路由：{self.router.describe()}",
            f"保管账：{self.ledger.describe()}",
        ]
        if self.broker.prefer_same_department:
            parts.append("平账优先级：同科室 → 全院")
        else:
            parts.append("平账优先级：全院（不分科室）")
        return "；".join(parts)


__all__ = ["MaterialPipeline"]
