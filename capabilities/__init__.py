"""中台层：可复用的能力中心。

与 ``business``（场景编排，回答「这件事怎么走完」）不同，中台回答的是
「这类事怎么算」，**不问场景**。同一个计量能力既服务教学实验，也服务
科研项目，还不知道调用它的是页面、脚本还是定时任务。

三个能力中心：

``metering``
    计量。配方 + 规模 → 需求单。含限制试剂判定、当量/配比/浓度换算。

``supply``
    供应。库存快照 → 可用量 → 缺口 → 采购建议。含保质期、管控、预占策略。

``circulation``
    流转。需求单 → 单据状态机。以网关抽象隔离「谁家的单据体系」，
    今天接 BCLRM 的三层单据，明天接科研的领用流，业务层不用改。

依赖方向：``platform`` 依赖 ``domain``，**不依赖** ``business`` /
``views`` / Streamlit。中台不认识「页面」和「用例」。
"""
from capabilities.metering.engine import MeteringEngine, MeteringError, MeteringResult
from capabilities.metering.resolver import (
    CatalogSubstanceResolver,
    SubstanceResolutionError,
    SubstanceResolver,
)
from capabilities.supply.availability import (
    Availability,
    AvailabilityPolicy,
    BorrowableOnly,
    HasQuantity,
    NotExpired,
    StandardAvailabilityPolicy,
    StrictAvailabilityPolicy,
)
from capabilities.supply.evaluator import SupplyAssessment, SupplyEvaluator, assess
from capabilities.supply.procurement import (
    PackCatalog,
    PackSpec,
    ProcurementPlanner,
    PurchaseProposal,
    PurchaseProposalLine,
    StaticPackCatalog,
)
from capabilities.supply.stock import ExpiryState, StockLot, StockSnapshot
from capabilities.circulation.gateway import (
    CirculationError,
    CirculationGateway,
    DemandTicket,
    GatewayNotReady,
    InMemoryCirculationGateway,
    TicketStatus,
)

__all__ = [
    # 计量
    "MeteringEngine", "MeteringError", "MeteringResult",
    "SubstanceResolver", "CatalogSubstanceResolver", "SubstanceResolutionError",
    # 供应
    "StockLot", "StockSnapshot", "ExpiryState",
    "Availability", "AvailabilityPolicy",
    "StandardAvailabilityPolicy", "StrictAvailabilityPolicy",
    "NotExpired", "BorrowableOnly", "HasQuantity",
    "SupplyEvaluator", "SupplyAssessment", "assess",
    "ProcurementPlanner", "PackCatalog", "PackSpec", "StaticPackCatalog",
    "PurchaseProposal", "PurchaseProposalLine",
    # 流转
    "CirculationGateway", "InMemoryCirculationGateway", "DemandTicket",
    "TicketStatus", "CirculationError", "GatewayNotReady",
]
