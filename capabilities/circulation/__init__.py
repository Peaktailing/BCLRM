"""流转能力中心：一条申请怎么从教师手上走到料配齐。

这个中心现在的形状是**两段**，不是一张单据的状态机。原因见
:mod:`domain.pipeline` 的模块说明——保管权决定了两段是不同性质的事：

- 第一段 ``AcceptanceDesk``：受理人只报自己名下够不够（保管权不变）
- 第二段 ``TransferBroker``：缺料的管理员去别的管理员名下平账（保管权流转）

``MaterialPipeline`` 把两段按唯一合法顺序串起来。``gateway`` 是早期
「单张票据」抽象，保留给不涉及保管权的简单场景（例如纯出库登记）。
"""
from capabilities.circulation.gateway import (
    CirculationError,
    CirculationGateway,
    DemandTicket,
    GatewayNotReady,
    InMemoryCirculationGateway,
    TicketEvent,
    TicketStatus,
)
from capabilities.circulation.ledger import (
    CustodyLedger,
    EmptyLedger,
    SnapshotLedger,
    ledger_of,
)
from capabilities.circulation.picking import HORIZON_DAYS, ReservePort, ShelfPolicy
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
from capabilities.circulation.stage2 import TransferBroker, broker_gaps

__all__ = [
    # 票据（不含保管权的简单场景）
    "CirculationError",
    "CirculationGateway",
    "DemandTicket",
    "GatewayNotReady",
    "InMemoryCirculationGateway",
    "TicketEvent",
    "TicketStatus",
    # 保管账
    "CustodyLedger",
    "SnapshotLedger",
    "EmptyLedger",
    "ledger_of",
    # 路由
    "RoutingError",
    "CustodianRouter",
    "StaticRouter",
    "SourceRouter",
    "DepartmentRouter",
    "CompositeRouter",
    # 两段
    "AcceptanceDesk",
    "TransferBroker",
    "broker_gaps",
    "MaterialPipeline",
    # 抽卡规则
    "ShelfPolicy",
    "ReservePort",
    "HORIZON_DAYS",
]
