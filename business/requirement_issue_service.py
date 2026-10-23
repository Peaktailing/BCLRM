"""需求单 → 借出单：逐项勾选、借出即兑付。

一张需求单走到「管理员愿意发」还没结束。料真的从架上扣下来、记在一张
领用单上，老师才拿到东西；也只有到那一刻，这张需求单的**那几项**才该
退出保底累计。

## 兑付的粒度是行，不是单头

v0.9.5 把整单一次性置 ``issued``，这在只有两项的小单上看不出问题，遇到
真实的一次课就露馅：一门课要 20 项，今天只到货 5 项。整单置 ``issued``
等于把那 15 项静默吞掉——状态不是 ``submitted``，保底不算它，待办列表也
不显示它，于是它永远没人管。

反过来，部分兑付后让单头继续停在 ``submitted``，保底又会按**全量**锁料：
已经发到老师手上的那 5 项被当成还没发的欠量，抽卡时不敢动，同一门课
第二周再申领就被自己上一张单压住。

两个错都出在「兑付挂错了对象」。所以：

    requirement_line.issued_quantity   累计已发（记回本行的单位）
    requirement_line.status            open / partial / issued
    requirement_line.order_number      最后一次兑付本行的借出单

单头状态只是这三者的聚合，不独立驱动：

    全部行 issued → issued；有行动过但没兑完 → partial；没动过 → 保持原状

``partial`` 是保底真正需要的那个状态：既说明「这张单还欠着」，又能按行
算余量，不再按全量压料。

## 不重算

瓶与数量取自 :class:`~domain.pipeline.Acceptance`——受理那一刻的判断。
此刻再算一遍会用到变了的库存，结论与当初承诺的不一致，事后对不上账。

## 余量截断

``Acceptance`` 是「那次受理时的实发量」。分两次发时第二次拿到的仍是同一个
数字，所以必须按 ``quantity − issued_quantity`` 截断，否则重复兑付同一批料。
截断发生在服务端，不信任调用方传来的量。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from business.borrow_service import borrow_service
from domain.pipeline import Acceptance, IssueLine
from domain.recipe import SourceKind
from domain.units import Quantity, parse_unit
from models.core.borrow_order import (
    APPROVAL_NOT_REQUIRED,
    ITEM_STATUS_PENDING,
    ORDER_STATUS_BORROWING,
    ORDER_TYPE_COURSE,
    ORDER_TYPE_SPORADIC,
)
from services.core.borrow_order_service import (
    borrow_order_item_service,
    borrow_order_service,
)
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.requirement_sheet_service import (
    LINE_ISSUED,
    SHEET_PARTIAL,
    requirement_line_service,
    requirement_sheet_service,
)
from utils.audit import audit
from utils.error_handler import ServiceResult, handle_exception, logger
from utils.field_mapper import RequirementSheetField

#: 这些状态下不再接受转单。``partial`` 不在其中——那正是还要继续发的意思。
_BLOCKED_STATUSES = ("issued", "closed", "cancelled")

#: 量的浮点容差。换算会带尾数，卡死等号会让行永远兑不完。
_EPS = 1e-9


class RequirementIssueService:
    """把受理结论按行落成借出单，每勾一项兑一项。"""

    def __init__(
        self,
        sheets=None,
        lines=None,
        orders=None,
        items=None,
        bottles=None,
        borrowers=None,
    ) -> None:
        self.sheets = sheets or requirement_sheet_service
        self.lines = lines or requirement_line_service
        self.orders = orders or borrow_order_service
        self.items = items or borrow_order_item_service
        self.bottles = bottles or reagent_bottle_service
        self.borrowers = borrowers or borrow_service

    # ---------------------------------------------------------------- 预览
    @handle_exception(context="需求单待签发项")
    def pending_rows(
        self, sheet_number: str, acceptance: Optional[Acceptance] = None
    ) -> ServiceResult:
        """这张单还能发什么：逐行给出需求 / 已发 / 余量 / 本次建议。

        页面拿这个渲染勾选表。``acceptance`` 为空时只报需求与已发（没有
        受理结论就不知道这次能抽到哪几瓶）。
        """
        row = self.sheets.get_by_number(sheet_number) if sheet_number else None
        if not row:
            return ServiceResult.fail(
                message=f"需求单不存在：{sheet_number}", error_code="SHEET_NOT_FOUND"
            )
        lines = self.sheets.lines_of(row[RequirementSheetField.ID])
        # 先做一遍正向匹配，得到「需求行 → 受理结论下标」。用同一套规则
        # 反查，避免预览与实际签发给出不同的对应关系。
        mapping: Dict[int, int] = {}
        if acceptance is not None:
            consumed: set = set()
            for index, line in enumerate(acceptance.issued):
                matched = self._match_line(lines, line, consumed)
                if matched is not None:
                    consumed.add(int(matched["id"]))
                    mapping[int(matched["id"])] = index

        rows: List[Dict[str, Any]] = []
        for line in lines:
            line_id = int(line["id"])
            need = float(line.get("quantity") or 0)
            done = float(line.get("issued_quantity") or 0)
            remaining = max(need - done, 0.0)
            index = mapping.get(line_id)
            suggestion = (
                float(acceptance.issued[index].quantity.to_float())
                if acceptance is not None and index is not None
                else 0.0
            )
            rows.append(
                {
                    "index": index,
                    "line_id": line_id,
                    "seq": int(line.get("seq") or 0),
                    "name": line.get("display_name") or line.get("substance_key") or "",
                    "unit": line.get("unit") or "",
                    "need": need,
                    "issued": done,
                    "remaining": remaining,
                    "status": line.get("status") or "open",
                    "suggest": min(suggestion, remaining),
                    "issuable": index is not None and remaining > _EPS and suggestion > _EPS,
                }
            )
        return ServiceResult.ok(
            data={
                "sheet_number": sheet_number,
                "status": (row.get(RequirementSheetField.STATUS) or "").strip(),
                "lines": rows,
                "pending": sum(1 for item in rows if item["remaining"] > _EPS),
            }
        )

    # ---------------------------------------------------------------- 主流程
    @handle_exception(context="需求单转借出单")
    def issue(
        self,
        sheet_number: str,
        acceptance: Acceptance,
        operator: str,
        note: str = "",
        selections: Optional[Sequence[int]] = None,
    ) -> ServiceResult:
        """按勾选的行转单 + 借出 + 兑付，三件事一个事务。

        Args:
            sheet_number: 需求单号（已落库的那张）
            acceptance: 第一段受理结论（必须带逐瓶分配）
            operator: 发料人（管理员）
            note: 备注，写进借出单
            selections: 勾选的行下标（``acceptance.issued`` 的下标）。
                ``None`` = 全部可发的行都发；传空序列 = 什么都不发。

        Returns:
            ServiceResult，``data`` 含 ``order_number`` / ``issued`` /
            ``failed`` / ``sheet_status``。
        """
        row = self.sheets.get_by_number(sheet_number) if sheet_number else None
        if not row:
            return ServiceResult.fail(
                message=f"需求单不存在：{sheet_number}", error_code="SHEET_NOT_FOUND"
            )
        status = (row.get(RequirementSheetField.STATUS) or "").strip()
        if status in _BLOCKED_STATUSES:
            return ServiceResult.fail(
                message=f"需求单 {sheet_number} 当前状态为「{status}」，不能转借出单",
                error_code="ALREADY_ISSUED" if status == LINE_ISSUED else "INVALID_SHEET_STATE",
            )

        line_rows = self.sheets.lines_of(row[RequirementSheetField.ID])
        if not line_rows:
            return ServiceResult.fail(
                message=(
                    f"需求单 {sheet_number} 没有明细行，无法逐项兑付。"
                    "请先重新保存这张需求单生成明细。"
                ),
                error_code="NO_LINES",
            )

        plan, skipped = self._plan(line_rows, acceptance, selections)
        if not plan:
            return ServiceResult.fail(
                message=(
                    "没有可签发的项："
                    + ("；".join(skipped) if skipped else "全部已兑付或都是缺口")
                ),
                error_code="NOTHING_TO_ISSUE",
                data={"skipped": skipped},
            )

        requester = acceptance.request.requester_name
        course_name, item_name = self._source_names(acceptance)
        order_number = self._next_order_number()

        borrowed: List[Dict[str, Any]] = []
        failed: List[str] = []
        settled: List[Dict[str, Any]] = []
        sheet_status = status
        try:
            with self.sheets.db.transaction():
                for item in plan:
                    for pick in item["picks"]:
                        result = self.borrowers.reagent_borrow(
                            bottle_number=pick["bottle_number"],
                            user=requester,
                            borrow_qty=pick["qty"],
                        )
                        if not result.is_success():
                            failed.append(f"{pick['bottle_number']}：{result.message}")
                            continue
                        borrowed.append(
                            {
                                "line_id": item["line_id"],
                                "bottle_number": pick["bottle_number"],
                                "reagent_name": item["name"],
                                "qty": pick["qty"],
                                "unit": pick["unit"],
                                "line_qty": pick["line_qty"],
                            }
                        )

                if not borrowed:
                    # 一项都没发出去：整单没有存在的意义，回滚
                    raise RuntimeError("借出全部失败：" + "；".join(failed))

                order_id = self.orders.create(
                    {
                        "order_number": order_number,
                        "order_type": (
                            ORDER_TYPE_COURSE
                            if acceptance.request.source
                            and acceptance.request.source.kind is SourceKind.TEACHING
                            else ORDER_TYPE_SPORADIC
                        ),
                        "applicant": requester,
                        "borrow_time": datetime.now().strftime("%Y/%m/%d %H:%M"),
                        "course_name": course_name,
                        "item_name": item_name,
                        "status": ORDER_STATUS_BORROWING,
                        "approval_status": APPROVAL_NOT_REQUIRED,
                        "remark": note or f"由需求单 {sheet_number} 转入",
                        "created_by": operator,
                        "requirement_number": sheet_number,
                    }
                )
                if not order_id:
                    raise RuntimeError("创建借出单失败")

                for pick in borrowed:
                    if not self.items.create(
                        {
                            "order_id": order_id,
                            "bottle_number": pick["bottle_number"],
                            "reagent_name": pick["reagent_name"],
                            "borrow_qty": pick["qty"],
                            "returned_qty": 0.0,
                            "unit": pick["unit"],
                            "status": ITEM_STATUS_PENDING,
                            "requirement_line_id": pick["line_id"],
                        }
                    ):
                        raise RuntimeError(f"创建借出单明细失败：{pick['bottle_number']}")

                # 逐行推进兑付量。同一行分了多瓶时先合并成一个数再推一次——
                # 推两次会让中间那次读到旧值，第二瓶被当成超额截掉。
                for line_id, amount in self._by_line(borrowed).items():
                    settled_row = self.lines.settle(line_id, amount, order_number)
                    if settled_row is None:
                        raise RuntimeError(f"更新需求行兑付量失败：line_id={line_id}")
                    settled.append({"line_id": line_id, **settled_row})

                self._anchor(row, order_number, operator)
                sheet_status = self.sheets.recount_status(
                    row[RequirementSheetField.ID]
                ) or status
        except Exception as exc:
            logger.error("需求单转借出单失败，已回滚", error=str(exc), exception=exc)
            if not borrowed:
                return ServiceResult.fail(
                    message=str(exc) or "转借出单失败", error_code="ISSUE_FAILED"
                )
            # 已经借出去的料收不回来，但单与兑付都没写成功——这种情况必须
            # 明说「账实可能不一致」，不能让调用方以为只是「部分失败」
            return ServiceResult.fail(
                message=f"借出已发生但落账失败，请人工核对：{exc}",
                error_code="LEDGER_WRITE_FAILED",
                data={"borrowed": borrowed},
            )

        parts = [f"已转借出单 {order_number}（{len(borrowed)} 瓶 / {len(settled)} 项）"]
        if failed:
            parts.append(f"{len(failed)} 瓶借出失败")
        if sheet_status == SHEET_PARTIAL:
            pending = sum(1 for item in settled if item["status"] != LINE_ISSUED)
            parts.append("需求单部分兑付，剩余项仍占保底")
        else:
            parts.append(f"需求单 {sheet_number} 已兑付")
        audit(
            operator,
            "需求单兑付",
            "requirement_sheet",
            sheet_number,
            f"借出单 {order_number}，{len(borrowed)} 瓶" + (f"，{len(failed)} 瓶失败" if failed else ""),
        )
        return ServiceResult.ok(
            data={
                "order_number": order_number,
                "order_id": order_id,
                "sheet_number": sheet_number,
                "sheet_status": sheet_status,
                "issued": borrowed,
                "failed": failed,
                "skipped": skipped,
                "settled": settled,
                "is_partial": bool(failed or skipped) or sheet_status == SHEET_PARTIAL,
            },
            message="；".join(parts),
        )

    # ---------------------------------------------------------------- 内部
    def _anchor(self, row: Dict[str, Any], order_number: str, operator: str) -> None:
        """首次兑付时在单头留一个锚点（首张借出单号 + 时刻 + 发料人）。

        后续再兑不覆盖：它是「这张单第一次转单」的入口，要换单号会让人以为
        前面那批料被改成了后面那张单。全部兑了哪些单，用
        ``borrow_order.requirement_number`` 反查。
        """
        if (row.get(RequirementSheetField.ORDER_NUMBER) or "").strip():
            return
        ok = self.sheets.update(
            row[RequirementSheetField.ID],
            {
                RequirementSheetField.ORDER_NUMBER: order_number,
                RequirementSheetField.ISSUED_AT: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                RequirementSheetField.ISSUED_BY: operator,
            },
        )
        if not ok:
            raise RuntimeError(f"回填需求单兑付锚点失败：{row.get('sheet_number')}")

    @staticmethod
    def _by_line(borrowed: List[Dict[str, Any]]) -> Dict[int, float]:
        """把逐瓶记录按需求行合并（保留插入顺序，便于日志与结果稳定）。"""
        totals: Dict[int, float] = {}
        for pick in borrowed:
            line_id = int(pick["line_id"])
            totals[line_id] = totals.get(line_id, 0.0) + float(pick["line_qty"])
        return totals

    def _plan(
        self,
        line_rows: List[Dict[str, Any]],
        acceptance: Acceptance,
        selections: Optional[Sequence[int]],
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """受理结论 → 逐行可执行清单。定位不到瓶的行不猜，记进 skipped。"""
        chosen = set(range(len(acceptance.issued))) if selections is None else set(selections)

        plan: List[Dict[str, Any]] = []
        skipped: List[str] = []
        consumed = set()  # 已配到受理结论的需求行，防同一行被配两次

        for index, line in enumerate(acceptance.issued):
            if index not in chosen:
                continue
            line_row = self._match_line(line_rows, line, consumed)
            if line_row is None:
                skipped.append(
                    f"{line.name}（序 {line.seq + 1}）：需求明细里找不到对应行，不能兑付"
                )
                continue
            consumed.add(int(line_row["id"]))

            remaining = self.lines.remaining_of(line_row)
            if remaining <= _EPS:
                skipped.append(f"{line.name}：已兑付完毕，不再重复签发")
                continue

            allocations = line.allocations()
            if not allocations:
                skipped.append(f"{line.name} {line.quantity.format(3)}：未指定具体瓶，需现场办理")
                continue

            picks, trimmed, missing = self._allocate(
                allocations, line_row, remaining, line
            )
            if not picks:
                skipped.append(
                    f"{line.name}：抽到的瓶与需求行单位不同量纲或数量无效，需现场办理"
                )
                continue
            for lot_id in missing:
                skipped.append(f"{lot_id}：试剂瓶不存在或已删除")
            if trimmed:
                skipped.append(
                    f"{line.name}：本次按剩余量 {remaining:g} {line_row.get('unit') or ''} 签发"
                    f"（受理时算的是 {line.quantity.format(3)}）"
                )
            plan.append(
                {
                    "index": index,
                    "line_id": int(line_row["id"]),
                    "name": line.name,
                    "picks": picks,
                }
            )
        return plan, skipped

    def _allocate(
        self,
        allocations: Sequence[Any],
        line_row: Dict[str, Any],
        remaining: float,
        line: IssueLine,
    ) -> tuple[List[Dict[str, Any]], bool, List[str]]:
        """把这一行的逐瓶分配按剩余量截断，并换算到每瓶自己的单位。

        截断按瓶的顺序吃：先发够的、再动下一瓶。不按比例分摊——比例分摊会
        让每瓶都扣一点零头，账面更难对。

        Returns:
            ``(picks, trimmed, missing)``。``missing`` 是找不到的瓶号，交给
            调用方如实写进 skipped——不猜、也不把份额挪给别的瓶。
        """
        row_unit = parse_unit(line_row.get("unit"), default=line.quantity.unit)
        if row_unit.dimension is not line.quantity.unit.dimension:
            return [], False, []

        budget = remaining
        picks: List[Dict[str, Any]] = []
        missing: List[str] = []
        trimmed = False
        for pick in allocations:
            if budget <= _EPS:
                trimmed = True
                break
            try:
                quantity = pick.quantity.to(row_unit)
            except Exception:
                continue
            amount = float(quantity.value)
            if amount <= _EPS:
                continue
            if amount > budget:
                amount = budget
                trimmed = True
            bottle = self.bottles.get_by_bottle_number(pick.lot_id)
            if not bottle:
                missing.append(pick.lot_id)
                continue  # 瓶没了，这一瓶跳过；预算不退，别把量挪给别的瓶
            in_bottle = self._in_bottle_unit(
                Quantity.of(amount, row_unit.symbol), bottle, line
            )
            if in_bottle is None or not in_bottle.is_positive():
                continue
            picks.append(
                {
                    "bottle_number": pick.lot_id,
                    "qty": in_bottle.to_float(),
                    "unit": in_bottle.unit.symbol,
                    "line_qty": amount,  # 记回需求行的单位，用于累计
                }
            )
            budget -= amount
        return picks, trimmed, missing

    @staticmethod
    def _match_line(
        line_rows: List[Dict[str, Any]], line: IssueLine, consumed: set
    ) -> Optional[Dict[str, Any]]:
        """受理行 → 需求行。先按 ``(物质, 序号)`` 精确配，再按物质兜底。

        序号在真实数据里可能重复（都是 0），所以物质键是主判据、序号只在
        同一物质出现多次时用来分拣。已经配出去的行不再复用——一条受理行
        只能兑一条需求行，否则一瓶料的量会被记到两项上。
        """
        pool = [
            row
            for row in line_rows
            if row.get("substance_key") == line.substance.key
            and int(row["id"]) not in consumed
        ]
        if not pool:
            return None
        for row in pool:
            if int(row.get("seq") or 0) == int(line.seq):
                return row
        return pool[0]

    @staticmethod
    def _in_bottle_unit(
        quantity: Quantity, bottle, line: IssueLine
    ) -> Optional[Quantity]:
        """把取量换算到瓶上记的单位。

        ``reagent_borrow`` 拿 float 与 ``remaining_quantity`` 直接比，单位错了
        不会报错，只会少扣或多扣——静默错账比报错难查得多。
        """
        bottle_unit = parse_unit(getattr(bottle, "unit", None), default=quantity.unit)
        if bottle_unit.dimension is not quantity.unit.dimension:
            logger.warning(
                f"{line.name} 的取量单位与瓶不一致，跳过",
                lot=quantity.unit.symbol,
                bottle=bottle_unit.symbol,
            )
            return None
        return quantity if quantity.unit is bottle_unit else quantity.to(bottle_unit)

    @staticmethod
    def _source_names(acceptance: Acceptance) -> tuple[str, str]:
        """来源「课程/实验」拆成两列。拆不出来就留空，不猜。"""
        source = acceptance.request.source
        if source is None or not source.code:
            return "", ""
        parts = [part.strip() for part in str(source.code).split("/")]
        if len(parts) >= 2:
            return parts[0], parts[1]
        return parts[0], ""

    @staticmethod
    def _next_order_number() -> str:
        """与工单同一前缀：借出单就是工单，不为需求单另造一套编号。"""
        return "BO" + datetime.now().strftime("%Y%m%d%H%M%S%f")


requirement_issue_service = RequirementIssueService()

__all__ = ["RequirementIssueService", "requirement_issue_service"]
