"""抽卡：从候选瓶里挑出最该动的那几瓶。

**尺度**：只在「当前周 + 下一周」这个窗口里做局部最优。窗口内的需求是
已知的、可枚举的；窗口外的需求还不存在，既算不出来，也不需要算。每过
一周窗口往后滚一格、重算一次——这就是 rolling horizon，也是「用局部最
优代替累计最优」能站住的前提：被截掉的那段本来就没有可靠输入。

**三个诉求里只有一个是目标**：

    需求要够      硬约束——填不满就是缺口，交给第二段，不是排序问题
    他还要够      硬约束——窗口内他自己要用的量不能被我抽走
    少开新瓶      软目标——排序键

约束先筛，目标后选。筛完的候选集里只剩单目标，于是局部键就等于最优：

- 若需求量 ≤ 已开封余量之和，新开瓶数下界是 0，任何「能不开就不开」的
  规则都达到下界，已是全局最优，不是近似；
- 若需求量更大，同规格下新瓶数下界是 ⌈(需求−已开封余量)/规格⌉，按下
  面的键抽正好达到；
- 只有多规格混存才退化为装箱近似，而那种场景在本系统里是少数。

**键必须是全序。** 末尾带瓶号不是装饰：两瓶到期日相同时，若比较到此为
止，谁先谁后取决于数据库返回顺序，同一个需求每次抽到的瓶都不一样，审
计对不上。``fefo_key`` 早就这么做了，新键继续保持。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Optional, Sequence

from capabilities.supply.stock import StockLot
from domain.custody import Custodian
from domain.pipeline import LotPick
from domain.substance import SubstanceRef
from domain.units import Quantity

#: 计算窗口：当前周 + 下一周。
HORIZON_DAYS = 14


@dataclass(frozen=True)
class ReserveQuery:
    """问一句「他在窗口内还要用多少」。

    打包成一个对象而不是三个位置参数：以后要加「只算某类用途」之类的
    维度时，不用改所有调用方。
    """

    custodian: Custodian
    substance: SubstanceRef
    #: 本次申请的来源（``source_kind``, ``source_code``）。同一来源的单要
    #: 排除掉，否则这张单会把自己算成自己的保底，一瓶都抽不出来。
    exclude_source: Optional[tuple[str, str]] = None


#: 保底查询端口。返回 None 表示「算不出来」或「没有保底」，两种都不锁料
#: ——保底是优化，不该成为发不出料的原因。
ReservePort = Callable[[ReserveQuery], Optional[Quantity]]


@dataclass(frozen=True)
class ShelfPolicy:
    """一套抽卡规则。无状态，可跨请求复用。

    Args:
        horizon_days: 计算窗口长度。窗口只用来界定「他要用的量」怎么算，
            不影响排序键本身——排序永远看全部候选瓶。
    """

    horizon_days: int = HORIZON_DAYS

    # ---------------------------------------------------------------- 时间窗
    def window(self, today: Optional[date] = None) -> tuple[date, date]:
        """返回 (起点, 截止日)，闭区间。默认从今天起算两周。"""
        start = today or date.today()
        return start, start + timedelta(days=self.horizon_days)

    # ---------------------------------------------------------------- 可抽量
    def drawable(
        self,
        lot: StockLot,
        pool: Quantity,
        reserved: Optional[Quantity] = None,
    ) -> Quantity:
        """这一瓶最多能抽多少，保证抽完「他还要的量」仍留得住。

        ``pool`` 是**该物质在该保管人名下的总量**，不是单瓶量。按瓶算
        「不能抽干」是错的：这一瓶抽完、旁边那瓶还在，完全合法。要守的
        是总量水位，所以上限 = 总量 − 留给他的量。
        """
        zero = Quantity.zero(lot.quantity.unit)
        keep = self._reserved(reserved, lot.quantity.unit)
        budget = pool - keep
        if budget.base_value() <= 0:
            return zero

        take = lot.quantity if lot.quantity.base_value() <= budget.base_value() else budget
        return take if take.is_positive() else zero

    # ---------------------------------------------------------------- 排序键
    def order_key(self, lot: StockLot, need: Quantity) -> tuple:
        """抽卡顺序。字典序，逐位决定，不做加权求和。

        第 1 位：临期/过期先出。这一位压过「省瓶」——临期瓶不在窗口内用
            掉就是报废，损失比多开一瓶大得多。它只在少量瓶上出现，不会
            破坏整体的省瓶效果。
        第 2 位：已开封先出。这是「少开新瓶」的落点。已开封的瓶开封后
            保质期本就缩短，先消耗它同时降低效期风险。
        第 3 位：一瓶够 > 要拼瓶。能用一瓶就别动两瓶。
        第 4 位：组内次序。一瓶够时余量越小越贴（少留半瓶）；要拼瓶时
            余量小的先出（先清空小瓶，半瓶数下降得更快）。
        第 5、6 位：原 FEFO 语义与全序兜底。
        """
        opened = lot.opened_on is not None
        enough = lot.quantity.base_value() >= need.base_value()
        if enough:
            # 越贴越好：抽完剩下的越少，这个瓶越接近清空
            fit = lot.quantity.base_value() - need.base_value()
        else:
            # 都装不满，先清小瓶
            fit = lot.quantity.base_value()

        return (
            lot.urgency,
            0 if opened else 1,
            0 if enough else 1,
            fit,
            lot.expires_on or date.max,
            lot.lot_id,
        )

    # ---------------------------------------------------------------- 主流程
    def pick(
        self,
        lots: Sequence[StockLot],
        need: Quantity,
        *,
        pool: Optional[Quantity] = None,
        reserved: Optional[Quantity] = None,
    ) -> tuple[LotPick, ...]:
        """从候选瓶里抽出满足 ``need`` 的量。

        Args:
            lots: 同物质、同量纲的候选批次（调用方已过滤好状态与归属）。
            need: 还差多少。
            pool: 该保管人名下该物质总量。省略时按 ``lots`` 求和。
            reserved: 窗口内他还要用、不能动的量。省略视为 0。

        Returns:
            按抽出顺序排列的 (瓶, 量)。抽不满时返回能抽到的部分——差额
            由调用方当作缺口处理，不在这里抛异常。
        """
        remaining = need
        if not remaining.is_positive() or not lots:
            return ()

        pool_total = pool if pool is not None else _sum_quantity(lots, need.unit)
        # 这次最多能抽多少。每抽一次从预算里扣，否则每瓶都按同一个上限
        # 算，会整体超抽——这是最容易写漏的一处。
        budget = pool_total - self._reserved(reserved, need.unit)

        candidates = [
            lot for lot in lots
            if lot.quantity.is_positive() and lot.quantity.unit.dimension is need.unit.dimension
        ]
        ordered = sorted(candidates, key=lambda lot: self.order_key(lot, need))

        picks: list[LotPick] = []
        for lot in ordered:
            if not remaining.is_positive() or budget.base_value() <= 0:
                break
            take = _smallest(lot.quantity, remaining, budget)
            if not take.is_positive():
                continue
            picks.append(LotPick(lot.lot_id, take))
            remaining = remaining - take
            budget = budget - take

        return tuple(picks)

    # ---------------------------------------------------------------- 内部
    @staticmethod
    def _reserved(reserved: Optional[Quantity], unit) -> Quantity:
        """把保底量对齐到目标量纲；对不上就当没有保底（不猜折算）。"""
        if reserved is None:
            return Quantity.zero(unit)
        if reserved.unit.dimension is not unit.dimension:
            return Quantity.zero(unit)
        return reserved


def _sum_quantity(lots: Sequence[StockLot], unit) -> Quantity:
    total = Quantity.zero(unit)
    for lot in lots:
        if lot.quantity.unit.dimension is unit.dimension:
            total = total + lot.quantity
    return total


def _smallest(*quantities: Quantity) -> Quantity:
    """按基准值取最小，保留原单位。"""
    return min(quantities, key=lambda q: q.base_value())


__all__ = ["ShelfPolicy", "HORIZON_DAYS", "ReservePort"]
