"""调配台：缺口 → 建议 → 对方点头 → 平账。

第一段兑付时手上不够，过去只有两条出路：少发（需求单停在 ``partial``）或者
等采购。院里别处有料，却没有任何通道——这个服务就是那条横向通道。

**调的是保管权，不是实物。** 走完一张调拨单，``reagent_bottle.manager`` 变了，
瓶子没动、库存总量没变。这是它与借还（不动 manager）、与采购（总量增加）
三者的分界。

四步分工：

| 步 | 谁 | 做什么 |
|---|---|---|
| ① 报缺口 | 缺料的管理员 | ``my_gaps`` 列出「我名下还没发出去的量」 |
| ② 撮合 | 中台 | ``propose`` 转调 ``TransferBroker``（那一层一行没改） |
| ③ 点头 | 出料的管理员本人 | ``accept`` / ``reject``，逐行勾选，同意即生效 |
| ④ 平账 | 系统 | 改 ``manager`` + 写 ``manager_change_log``（``ref_type=transfer_order``） |

**为什么不复用 ``allocation_order``**：那张单是 demand 驱动的「智能分配算
够不够」，没有出料人、没有双方确认、明细只有瓶号文本。把保管权流转塞进去，
一张表会同时背两套语义，往后谁都读不懂它的状态。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from business.manager_service import manager_service, REASON_ALLOCATION
from business.material_pipeline_service import material_pipeline_service
from business.requirement_issue_service import requirement_issue_service
from domain.batch import BatchScale
from domain.custody import Custodian
from domain.pipeline import Acceptance, Shortfall, TeacherRequest
from domain.recipe import SourceKind, SourceRef
from domain.requirement import ComponentRole, RequirementLine, RequirementSheet
from domain.substance import SubstanceRef
from domain.transfer import (
    ITEM_PENDING,
    ORIGIN_SHEET,
    REASON_FORCED,
    REASON_MANUAL,
    REASON_SHORTFALL,
    TRANSFER_ACCEPTED,
    TRANSFER_REJECTED,
    TRANSFER_REQUESTED,
    answer_blocked_reason,
    can_answer,
    can_cancel,
    can_reject,
    check_parties,
    resolve_selections,
)
from domain.units import Quantity, parse_unit
from services.base.work_group_service import work_group_service
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.requirement_sheet_service import requirement_sheet_service
from services.core.transfer_order_service import transfer_order_service
from utils.error_handler import ServiceResult, handle_exception, logger

_EPS = 1e-9
#: 「还有缺口可调」的单状态。兑付完的单不再出现在缺口列表里。
_GAP_STATUSES = ("submitted", "partial")


class TransferService:
    """调配台业务服务（页面只调这里，不直接碰 broker 与单据表）"""

    def __init__(
        self,
        sheets=None,
        issues=None,
        orders=None,
        pipeline=None,
        managers=None,
        bottles=None,
    ) -> None:
        self.sheets = sheets or requirement_sheet_service
        self.issues = issues or requirement_issue_service
        self.orders = orders or transfer_order_service
        self.pipeline = pipeline or material_pipeline_service
        self.managers = managers or manager_service
        self.bottles = bottles or reagent_bottle_service

    # ---------------------------------------------------------------- 缺口
    @handle_exception(context="我的缺口")
    def my_gaps(self, me: str) -> ServiceResult:
        """我名下还没发出去的量（只认 ``person`` 归属的单）。

        组池与全院池的单还没有主人，缺口也就没有主人——谁先认领谁负责调。
        把池子里的单也算成「我的缺口」，会变成每个人都以为别人去调了。
        """
        me = (me or "").strip()
        if not me:
            return ServiceResult.fail(message="未登录，无法查看缺口", error_code="NO_USER")
        gaps: List[Dict[str, Any]] = []
        for row in self.sheets.list_by_custodian(me, _GAP_STATUSES):
            lines = self._gap_lines(row)
            if not lines:
                continue
            gaps.append(
                {
                    "sheet_number": row.get("sheet_number"),
                    "title": row.get("title"),
                    "requester": row.get("requester"),
                    "status": (row.get("status") or "").strip(),
                    "lines": lines,
                    "shortfall": sum(item["remaining"] for item in lines),
                }
            )
        return ServiceResult.ok(data=gaps, message=f"共 {len(gaps)} 张单还有缺口")

    @handle_exception(context="单据缺口")
    def gap_of(self, sheet_number: str, me: str = "") -> ServiceResult:
        """一张单的缺口明细（页面展开单张时用）。"""
        row = self.sheets.get_by_number(sheet_number) if sheet_number else None
        if not row:
            return ServiceResult.fail(
                message=f"需求单不存在：{sheet_number}", error_code="SHEET_NOT_FOUND"
            )
        lines = self._gap_lines(row)
        if not lines:
            return ServiceResult.fail(
                message="这张单已经没有缺口（全部兑付完或尚未受理）",
                error_code="NOTHING_TO_TRANSFER",
            )
        return ServiceResult.ok(
            data={
                "sheet_number": row.get("sheet_number"),
                "title": row.get("title"),
                "requester": row.get("requester"),
                "status": (row.get("status") or "").strip(),
                "custodian": row.get("custodian_key") or "",
                "lines": lines,
            }
        )

    # ---------------------------------------------------------------- 撮合
    @handle_exception(context="撮合调拨建议")
    def propose(self, sheet_number: str, me: str) -> ServiceResult:
        """缺口 → 建议（谁给、给哪几瓶、多少）。

        直接转调 ``material_pipeline_service.settle``：撮合规则只应该有一份，
        页面换个入口就换一套算法，是最容易埋雷的写法。
        """
        gap = self.gap_of(sheet_number)
        if not gap.success:
            return gap
        row = self.sheets.get_by_number(sheet_number)
        acceptance = self._acceptance_of(row, gap.data["lines"], me)
        settled = self.pipeline.settle(acceptance)
        if not settled.success:
            return settled
        proposal = settled.data["proposal"]

        groups: Dict[str, Dict[str, Any]] = {}
        for line in proposal.lines:
            bucket = groups.setdefault(
                line.from_custodian.name,
                {
                    "supplier": line.from_custodian.name,
                    "department": line.from_custodian.department,
                    "priority": line.priority,
                    "cross_department": line.is_cross_department,
                    "lines": [],
                },
            )
            bucket["lines"].append(
                {
                    "lot_id": line.lot_id,
                    "substance_key": line.substance.key,
                    "cas_number": line.substance.cas.value if line.substance.cas else "",
                    "name": line.name,
                    "quantity": line.quantity.to_float(),
                    "unit": line.quantity.unit.symbol,
                    "note": line.note,
                }
            )
        ordered = sorted(groups.values(), key=lambda item: (item["priority"], item["supplier"]))
        return ServiceResult.ok(
            data={
                "proposal": proposal,
                "acceptance": acceptance,
                "groups": ordered,
                "unresolved": [
                    {"name": item.name, "quantity": item.quantity.to_float(),
                     "unit": item.quantity.unit.symbol, "reason": item.reason}
                    for item in proposal.unresolved
                ],
                "purchase_sheet": proposal.purchase_sheet(),
            },
            message=proposal.describe(),
        )

    # ---------------------------------------------------------------- 发起
    @handle_exception(context="发起调拨")
    def request(
        self,
        sheet_number: str,
        supplier: str,
        me: str,
        note: str = "",
        reason: str = REASON_SHORTFALL,
        line_indexes: Optional[Sequence[int]] = None,
    ) -> ServiceResult:
        """把某个出料人的一部分建议落成一张调拨单（一人一单）。

        每次调用都**重算**建议，不接收页面传回来的数量：页面上的数字是上一次
        渲染的产物，中间别人可能已经发过料。数量以此刻的账为准。
        """
        supplier = (supplier or "").strip()
        if not supplier:
            return ServiceResult.fail(message="未指定出料人", error_code="NO_SUPPLIER")
        bad = check_parties(supplier, me)
        if bad == "SAME_MANAGER":
            return ServiceResult.fail(
                message="出料人和受益人是同一个人，无需调配", error_code=bad
            )
        if bad:
            return ServiceResult.fail(message="出料人或受益人为空", error_code=bad)

        proposed = self.propose(sheet_number, me)
        if not proposed.success:
            return proposed
        group = next(
            (item for item in proposed.data["groups"] if item["supplier"] == supplier), None
        )
        if group is None:
            return ServiceResult.fail(
                message=f"「{supplier}」名下当前没有可调的量（可能刚被借走）",
                error_code="SUPPLIER_EMPTY",
            )

        picked = group["lines"]
        if line_indexes is not None:
            chosen = {int(i) for i in line_indexes}
            picked = [line for i, line in enumerate(picked) if i in chosen]
        if not picked:
            return ServiceResult.fail(message="一行都没选", error_code="NO_LINE_SELECTED")

        items = self._split_items(picked)
        if not items:
            return ServiceResult.fail(message="没有可执行的瓶", error_code="NO_TRANSFER_ITEM")
        order = self.orders.create_order(
            from_manager=supplier,
            to_manager=me,
            lines=items,
            requested_by=me,
            reason=reason,
            origin_kind=ORIGIN_SHEET,
            origin_ref=sheet_number,
            note=note,
            status=TRANSFER_REQUESTED,
        )
        if order is None:
            return ServiceResult.fail(message="调拨单建单失败", error_code="CREATE_FAILED")
        logger.info(
            f"调拨已发起 {order.transfer_number}：{supplier} → {me}"
            f"（{len(items)} 瓶，源 {sheet_number}）"
        )
        return ServiceResult.ok(
            data={"order": order},
            message=(
                f"已发给「{supplier}」点头：{len(items)} 瓶，单号 {order.transfer_number}"
            ),
        )

    # ---------------------------------------------------------------- 点头
    @handle_exception(context="同意调拨")
    def accept(
        self,
        transfer_id: int,
        me: str,
        selections: Optional[Iterable[int]] = None,
        remark: str = "",
        is_super_admin: bool = False,
    ) -> ServiceResult:
        """点头：逐行勾选，同意即生效（改保管权）。"""
        order = self.orders.get(transfer_id)
        if order is None:
            return ServiceResult.fail(message="调拨单不存在", error_code="NOT_FOUND")
        blocked = answer_blocked_reason(
            order.status, order.from_manager, me, is_super_admin
        )
        if blocked:
            return ServiceResult.fail(
                message=blocked,
                error_code="NOT_ALLOWED",
                data={"status": order.status, "from_manager": order.from_manager},
            )
        accepted, declined = resolve_selections(len(order.items), selections)
        if not accepted:
            return ServiceResult.fail(
                message="一行都没勾——要整单拒绝请用「不同意」并写理由",
                error_code="NO_LINE_SELECTED",
            )
        forced = bool(is_super_admin) and (me or "").strip() != (order.from_manager or "").strip()
        applied = self.orders.commit_answer(
            transfer_id,
            accepted,
            declined,
            me,
            remark,
            status=TRANSFER_ACCEPTED,
            forced=forced,
            apply_line=lambda item: self._apply_line(order, item),
        )
        if applied.get("late"):
            return ServiceResult.fail(
                message="这张单已经被处理过了，刷新看看最新状态",
                error_code="ALREADY_ANSWERED",
            )
        failed = applied.get("failed") or []
        parts = [f"{order.transfer_number}：已转 {len(applied.get('applied') or [])} 瓶"]
        if declined:
            parts.append(f"{len(declined)} 瓶没同意")
        if failed:
            parts.append(
                f"{len(failed)} 瓶没转成（" + "；".join(
                    f"{row['lot_id'] or '现场指定'}：{row['reason']}" for row in failed
                ) + "）"
            )
        message = "，".join(parts)
        data = dict(applied)
        data["order"] = self.orders.get(transfer_id)
        if failed and not applied.get("applied"):
            return ServiceResult.fail(
                message=message, error_code="TRANSFER_FAILED", data=data
            )
        return ServiceResult.ok(data=data, message=message)

    @handle_exception(context="拒绝调拨")
    def reject(
        self, transfer_id: int, me: str, remark: str, is_super_admin: bool = False
    ) -> ServiceResult:
        """不同意：必填理由（与「退回不写原因」相反，见 domain 里的说明）。"""
        order = self.orders.get(transfer_id)
        if order is None:
            return ServiceResult.fail(message="调拨单不存在", error_code="NOT_FOUND")
        blocked = answer_blocked_reason(
            order.status, order.from_manager, me, is_super_admin
        )
        if blocked:
            return ServiceResult.fail(message=blocked, error_code="NOT_ALLOWED")
        bad = can_reject(order.status, remark)
        if bad == "REJECT_REMARK_REQUIRED":
            return ServiceResult.fail(
                message="拒绝要写一句理由——对方得知道是「没有」还是「不给」",
                error_code=bad,
            )
        if bad:
            return ServiceResult.fail(message=f"当前状态不能拒绝（{order.status}）", error_code=bad)
        applied = self.orders.commit_answer(
            transfer_id,
            [],
            list(range(len(order.items))),
            me,
            remark,
            status=TRANSFER_REJECTED,
        )
        if applied.get("late"):
            return ServiceResult.fail(
                message="这张单已经被处理过了，刷新看看最新状态",
                error_code="ALREADY_ANSWERED",
            )
        return ServiceResult.ok(
            data={"order": self.orders.get(transfer_id)},
            message=f"{order.transfer_number} 已拒绝：{remark}",
        )

    @handle_exception(context="撤回调拨")
    def cancel(self, transfer_id: int, me: str, remark: str = "",
               is_super_admin: bool = False) -> ServiceResult:
        order = self.orders.get(transfer_id)
        if order is None:
            return ServiceResult.fail(message="调拨单不存在", error_code="NOT_FOUND")
        if not can_cancel(order.status, order.requested_by, me, is_super_admin):
            return ServiceResult.fail(
                message=f"只有发起人能撤回还没被点头的单（当前：{order.status}）",
                error_code="NOT_ALLOWED",
            )
        if not self.orders.cancel(transfer_id, me, remark):
            return ServiceResult.fail(
                message="这张单已经被处理过了，刷新看看最新状态",
                error_code="ALREADY_ANSWERED",
            )
        return ServiceResult.ok(message=f"{order.transfer_number} 已撤回")

    @handle_exception(context="标记实物已取走")
    def mark_picked_up(self, transfer_id: int) -> ServiceResult:
        """实物取走（可选）。账上在点头那一刻就生效了，这一笔只记实物。"""
        order = self.orders.get(transfer_id)
        if order is None:
            return ServiceResult.fail(message="调拨单不存在", error_code="NOT_FOUND")
        if (order.status or "") != TRANSFER_ACCEPTED:
            return ServiceResult.fail(
                message=f"这张单还没生效（{order.status}），谈不上取货",
                error_code="NOT_EFFECTIVE",
            )
        if order.picked_up_at:
            return ServiceResult.ok(message="已经记过取货时间了")
        self.orders.mark_picked_up(transfer_id)
        return ServiceResult.ok(message=f"{order.transfer_number}：已记下实物取走")

    # ---------------------------------------------------------------- 视图
    @handle_exception(context="待我点头的调拨")
    def pending_for(self, me: str) -> ServiceResult:
        orders = self._with_items(self.orders.list_pending_for(me))
        return ServiceResult.ok(data=orders, message=f"共 {len(orders)} 张等我点头")

    @handle_exception(context="我发起的调拨")
    def mine(self, me: str, include_closed: bool = False) -> ServiceResult:
        orders = self._with_items(self.orders.list_mine(me, include_closed))
        return ServiceResult.ok(data=orders)

    @handle_exception(context="全院在办调拨")
    def open_all(self) -> ServiceResult:
        orders = self._with_items(self.orders.list_open())
        return ServiceResult.ok(data=orders)

    @handle_exception(context="调配台计数")
    def summary(self, me: str) -> ServiceResult:
        """页面顶部三档：我欠别人的 / 别人欠我的 / 全院在办。"""
        me = (me or "").strip()
        pending = self.orders.list_pending_for(me)
        mine = self.orders.list_mine(me)
        waiting = [order for order in mine if (order.status or "") == TRANSFER_REQUESTED]
        gaps = self.my_gaps(me)
        return ServiceResult.ok(
            data={
                "pending_for_me": len(pending),
                "waiting_for_others": len(waiting),
                "open_all": len(self.orders.list_open()),
                "my_gaps": len(gaps.data or []),
            }
        )

    # ---------------------------------------------------------------- 内部
    def _with_items(self, orders: Sequence[Any]) -> List[Any]:
        for order in orders:
            order.items = self.orders.items_of(order.id)
        return list(orders)

    def _gap_lines(self, sheet_row: Dict[str, Any]) -> List[Dict[str, Any]]:
        """需求行 − 已兑付 = 缺口。与 `pending_rows` 同一套余量口径。"""
        sheet_id = sheet_row.get("id")
        if not sheet_id:
            return []
        rows: List[Dict[str, Any]] = []
        for line in self.sheets.lines_of(sheet_id):
            remaining = self.issues.lines.remaining_of(line)
            if remaining <= _EPS:
                continue
            rows.append(
                {
                    "line_id": line.get("id"),
                    "seq": int(line.get("seq") or 0),
                    "substance_key": line.get("substance_key") or "",
                    "cas_number": line.get("cas_number") or "",
                    "name": line.get("display_name") or line.get("substance_key") or "",
                    "unit": line.get("unit") or "",
                    "need": float(line.get("quantity") or 0),
                    "issued": float(line.get("issued_quantity") or 0),
                    "remaining": remaining,
                    "role": line.get("role") or "",
                    "controlled": bool(line.get("is_controlled") or 0),
                }
            )
        return rows

    def _acceptance_of(
        self, sheet_row: Dict[str, Any], gap_lines: Sequence[Dict[str, Any]], me: str
    ) -> Acceptance:
        """把库里的一张单还原成「受理结论」，好让第二段接着算。

        这一步不能省：``TransferBroker`` 的入参是 ``Acceptance``，而它需要的
        只是「谁受理的、要什么、缺多少」。库里存的是行，这里把行拼回领域对象，
        中台一行都不改。
        """
        requirements = []
        shortfalls = []
        for item in gap_lines:
            unit = parse_unit(item["unit"]) if item["unit"] else parse_unit("g")
            try:
                role = ComponentRole(item["role"]) if item["role"] else ComponentRole.REAGENT
            except ValueError:
                role = ComponentRole.REAGENT
            substance = SubstanceRef.of(item["name"], item["cas_number"] or None)
            line = RequirementLine(
                substance=substance,
                role=role,
                quantity=Quantity.of(item["need"], unit),
                seq=int(item["seq"]),
                controlled=bool(item["controlled"]),
            )
            requirements.append(line)
            shortfalls.append(
                Shortfall(
                    requirement=line,
                    quantity=Quantity.of(item["remaining"], unit),
                    reason="名下不足",
                )
            )
        source = self._source_of(sheet_row)
        sheet = RequirementSheet(
            recipe_key=sheet_row.get("recipe_key") or "transfer:gap",
            title=sheet_row.get("title") or "缺口调配",
            scale=BatchScale.single(),
            lines=tuple(requirements),
            source=source,
        )
        groups = work_group_service.groups_of((me or "").strip())
        return Acceptance(
            custodian=Custodian.of((me or "").strip(), groups[0] if groups else ""),
            request=TeacherRequest(
                requester=(me or "").strip(),
                sheet=sheet,
                source=source,
                note=f"缺口调配，源单 {sheet_row.get('sheet_number') or ''}",
            ),
            issued=(),
            shortfalls=tuple(shortfalls),
        )

    @staticmethod
    def _source_of(sheet_row: Dict[str, Any]) -> Optional[SourceRef]:
        kind_text = (sheet_row.get("source_kind") or "").strip()
        code = (sheet_row.get("source_code") or "").strip()
        if not kind_text and not code:
            return None
        try:
            kind = SourceKind(kind_text)
        except ValueError:
            kind = SourceKind.MANUAL
        return SourceRef(kind=kind, code=code)

    def _split_items(self, lines: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把建议的一行拆成「一瓶一行」，量按瓶的顺序吃。

        建议里的 ``lot_id`` 可能是 ``"A,B"``（一行要动两瓶），而调拨单必须
        精确到瓶——不拆的话，执行时只能写「A、B 共 100 g」，扣哪瓶扣多少
        全靠现场猜。这与第一段逐瓶落单是同一个道理。
        """
        items: List[Dict[str, Any]] = []
        for line in lines:
            lot_ids = [part.strip() for part in (line.get("lot_id") or "").split(",") if part.strip()]
            total = float(line.get("quantity") or 0)
            if not lot_ids:
                # 现场指定：不知道是哪一瓶，整行留给人工办理
                items.append(self._item_of(line, "", total))
                continue
            left = total
            for lot_id in lot_ids:
                if left <= _EPS:
                    break
                take = left
                bottle = self.bottles.get_by_bottle_number(lot_id)
                if bottle is not None:
                    available = float(getattr(bottle, "remaining_quantity", 0) or 0)
                    take = min(left, available) if available > 0 else left
                items.append(self._item_of(line, lot_id, take))
                left -= take
            if left > _EPS:
                # 瓶里的量比建议少（刚被借走一部分）：把差额补在末行上，
                # 宁可少转也不虚增——多出来的量会在执行时被 SAME_MANAGER 挡住
                items.append(self._item_of(line, "", left))
        return [item for item in items if (item["quantity"] or 0) > _EPS]

    @staticmethod
    def _item_of(line: Dict[str, Any], lot_id: str, quantity: float) -> Dict[str, Any]:
        return {
            "lot_id": lot_id,
            "substance_key": line.get("substance_key") or "",
            "cas_number": line.get("cas_number") or "",
            "display_name": line.get("name") or "",
            "quantity": quantity,
            "unit": line.get("unit") or "",
            "note": line.get("note") or "",
        }

    def _apply_line(self, order: Any, item: Any):
        """把一瓶的保管权转过去。返回 (成功, 原因)。

        调的还是 ``manager_service.transfer`` 这个原语——它已经会拒绝在借瓶
        （``BOTTLE_NOT_BORROWABLE``）与「已是本人」（``SAME_MANAGER``）。这里
        只把失败翻译成一句人话，不改判定。
        """
        if not item.lot_id:
            return False, "未指定具体瓶，需现场办理"
        reason = REASON_SHORTFALL
        if order.forced:
            reason = REASON_FORCED
        elif (order.reason or "") == REASON_MANUAL:
            reason = REASON_MANUAL
        result = self.managers.transfer(
            item.lot_id,
            order.to_manager,
            order.respondent or order.from_manager,
            reason=reason or REASON_ALLOCATION,
            remark=order.answer_remark or "",
            ref_type="transfer_order",
            ref_id=order.transfer_number,
        )
        if result.is_success():
            return True, ""
        return False, result.message


transfer_service = TransferService()

__all__ = ["TransferService", "transfer_service"]
