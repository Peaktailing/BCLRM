"""需求单 → 借出单：借出即兑付。

一张需求单走到「管理员愿意发」还没结束。料真的从架上扣下来、记在一张
领用单上，老师才拿到东西；也只有到那一刻，这张需求单才该退出保底累计。

不这么做的后果在 v0.9.4 里已经出现过：保底只认 ``submitted``，而发完料
状态不动，于是同一门课第二周再申领时，上一张单还挂在学年里占着量，两张
单互相压。学年解决了「跨年累计」，兑付解决「同学年内重复占量」。

所以转单与兑付是一个动作，拆成两步只会留下「有单没发、账已占着」的中间态：

    需求单（受理结论，逐瓶）
        → borrow_order + borrow_order_item（一单多瓶）
        → 逐瓶 reagent_borrow（扣库存，写领用流水）
        → 需求单 status=issued + 借出单号 + 兑付时刻

**不重算**。瓶与数量取自 :class:`~domain.pipeline.Acceptance`——受理那一刻
的判断。此刻再算一遍会用到变了的库存，结论与当初承诺的不一致，事后对不上账。

**部分失败不回滚整单**。料可能已经交到老师手上，账必须留下：成功的落单，
失败的如实报告。整行都没有具体瓶号（跨量纲或现场指定）时不猜——那种行
不进借出单，由人工办理，这一点与第二段执行调拨的处理一致。
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
from services.core.requirement_sheet_service import requirement_sheet_service
from utils.audit import audit
from utils.error_handler import ServiceResult, handle_exception, logger
from utils.field_mapper import RequirementSheetField

#: 这些状态下不再接受转单。``draft`` 不在其中——页面生成的需求单就是 draft，
#: 中间没有强制的「提交」动作，硬卡会把正常流程堵死。
_BLOCKED_STATUSES = ("issued", "closed", "cancelled")


class RequirementIssueService:
    """把受理结论落成借出单，并在借出的同一刻完成兑付。"""

    def __init__(
        self,
        sheets=None,
        orders=None,
        items=None,
        bottles=None,
        borrowers=None,
    ) -> None:
        self.sheets = sheets or requirement_sheet_service
        self.orders = orders or borrow_order_service
        self.items = items or borrow_order_item_service
        self.bottles = bottles or reagent_bottle_service
        self.borrowers = borrowers or borrow_service

    # ---------------------------------------------------------------- 主流程
    @handle_exception(context="需求单转借出单")
    def issue(
        self,
        sheet_number: str,
        acceptance: Acceptance,
        operator: str,
        note: str = "",
    ) -> ServiceResult:
        """转单 + 借出 + 兑付，三件事一个事务。

        Args:
            sheet_number: 需求单号（已落库的那张）
            acceptance: 第一段受理结论（必须带逐瓶分配）
            operator: 发料人（管理员）
            note: 备注，写进借出单

        Returns:
            ServiceResult，``data`` 含 ``order_number`` / ``issued`` / ``failed``。
        """
        row = self.sheets.get_by_number(sheet_number) if sheet_number else None
        if not row:
            return ServiceResult.fail(
                message=f"需求单不存在：{sheet_number}", error_code="SHEET_NOT_FOUND"
            )
        if (row.get(RequirementSheetField.ORDER_NUMBER) or "").strip():
            return ServiceResult.fail(
                message=(
                    f"需求单 {sheet_number} 已兑付（借出单 "
                    f"{row.get(RequirementSheetField.ORDER_NUMBER)}），不能重复转单"
                ),
                error_code="ALREADY_ISSUED",
            )
        status = (row.get(RequirementSheetField.STATUS) or "").strip()
        if status in _BLOCKED_STATUSES:
            return ServiceResult.fail(
                message=f"需求单 {sheet_number} 当前状态为「{status}」，不能转借出单",
                error_code="INVALID_SHEET_STATE",
            )

        plan, skipped = self._plan(acceptance)
        if not plan:
            return ServiceResult.fail(
                message=(
                    "受理结论里没有可执行的瓶："
                    + ("；".join(skipped) if skipped else "全部是缺口")
                ),
                error_code="NOTHING_TO_ISSUE",
                data={"skipped": skipped},
            )

        requester = acceptance.request.requester_name
        course_name, item_name = self._source_names(acceptance)
        order_number = self._next_order_number()

        borrowed: List[Dict[str, Any]] = []
        failed: List[str] = []
        try:
            with self.sheets.db.transaction():
                for pick in plan:
                    result = self.borrowers.reagent_borrow(
                        bottle_number=pick["bottle_number"],
                        user=requester,
                        borrow_qty=pick["qty"],
                    )
                    if result.is_success():
                        borrowed.append(pick)
                    else:
                        failed.append(f"{pick['bottle_number']}：{result.message}")

                if not borrowed:
                    # 一瓶都没发出去：整单没有存在的意义，回滚
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
                        }
                    ):
                        raise RuntimeError(f"创建借出单明细失败：{pick['bottle_number']}")

                self._settle(row, order_number, operator)
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

        parts = [f"已转借出单 {order_number}（{len(borrowed)} 瓶）"]
        if failed:
            parts.append(f"{len(failed)} 瓶借出失败")
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
                "issued": borrowed,
                "failed": failed,
                "skipped": skipped,
                "is_partial": bool(failed or skipped),
            },
            message="；".join(parts),
        )

    # ---------------------------------------------------------------- 内部
    def _settle(self, row: Dict[str, Any], order_number: str, operator: str) -> None:
        """把需求单推到「已兑付」。与借出同一事务，不允许只有单没有状态。"""
        ok = self.sheets.update(
            row[RequirementSheetField.ID],
            {
                RequirementSheetField.STATUS: "issued",
                RequirementSheetField.ORDER_NUMBER: order_number,
                RequirementSheetField.ISSUED_AT: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                RequirementSheetField.ISSUED_BY: operator,
            },
        )
        if not ok:
            raise RuntimeError(f"更新需求单 {row.get('sheet_number')} 状态失败")

    def _plan(self, acceptance: Acceptance) -> tuple[List[Dict[str, Any]], List[str]]:
        """受理结论 → 逐瓶可执行清单。定位不到瓶的行不猜，记进 skipped。"""
        plan: List[Dict[str, Any]] = []
        skipped: List[str] = []
        for line in acceptance.issued:
            allocations = line.allocations()
            if not allocations:
                skipped.append(f"{line.name} {line.quantity.format(3)}：未指定具体瓶，需现场办理")
                continue
            for pick in allocations:
                bottle = self.bottles.get_by_bottle_number(pick.lot_id)
                if not bottle:
                    skipped.append(f"{pick.lot_id}：试剂瓶不存在或已删除")
                    continue
                quantity = self._in_bottle_unit(pick.quantity, bottle, line)
                if quantity is None or not quantity.is_positive():
                    skipped.append(f"{pick.lot_id}：数量无效（{pick.quantity.format(3)}）")
                    continue
                plan.append(
                    {
                        "bottle_number": pick.lot_id,
                        "reagent_name": line.name,
                        "qty": quantity.to_float(),
                        "unit": quantity.unit.symbol,
                    }
                )
        return plan, skipped

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
