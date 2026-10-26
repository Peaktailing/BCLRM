"""需求单的管制试剂双人复核。

## 为什么需求单也要两签

管制化学品的合规要求是「两个人看过」，与单子从哪个入口进来无关。工单那边
的第一签在 ``approve_order`` 里，第二签在 ``approve_second`` 里；需求单这条
路没有「审批」这个动作（兑付就是发料），所以复核必须**在兑付之前**完成：

    受理（认领的管理员算量、定瓶）
      → 送复核（指定另一名管理员）
      → 复核通过
      → 兑付（此时才扣库存）

顺序不能倒。先发料再补签，签的是「已经发生的事」，双人审批就成了事后追认。

## 一轮一签

复核结论只管**这一次兑付**：兑付成功后 ``second_approval_status`` 清空，
下一批料要重新送复核。理由很直接——第一批是三瓶乙醇，第二批可能是两瓶
乙醚，上一次那双眼睛没看过这批清单。

## 复核人不看归属

认的是「被指定的那个人」，不是「单归谁」。换了归属就换复核人，等于让审批
人自己挑裁判。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from models.core.borrow_order import SECOND_APPROVED, SECOND_PENDING
from services.base.person_service import person_service
from services.core.requirement_sheet_service import requirement_sheet_service
from utils.audit import audit
from utils.error_handler import ServiceResult, handle_exception, logger
from utils.field_mapper import RequirementSheetField

ADMIN_ROLES = ("admin", "super_admin")

#: 还在办、可以送复核的状态
OPEN_STATUSES = ("submitted", "partial")


class RequirementReviewService:
    """送复核 / 复核通过。"""

    def __init__(self, sheets=None, people=None) -> None:
        self.sheets = sheets or requirement_sheet_service
        self.people = people or person_service

    # ---------------------------------------------------------------- 读
    def _role_of(self, name: Optional[str]) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        person = self.people.get_by_name(name)
        return (getattr(person, "role", "") or "").strip() if person else ""

    def is_admin(self, name: Optional[str]) -> bool:
        return self._role_of(name) in ADMIN_ROLES

    def is_approved(self, sheet: Optional[Dict[str, Any]]) -> bool:
        """这张单当前的复核是否有效。"""
        if not sheet:
            return False
        return (sheet.get("second_approval_status") or "").strip() == SECOND_APPROVED

    def pending_for(self, approver: str) -> List[Dict[str, Any]]:
        """等这个人复核的单。"""
        approver = (approver or "").strip()
        if not approver:
            return []
        return self.sheets.db.execute_query(
            "SELECT * FROM requirement_sheet WHERE second_approver = ? "
            "AND COALESCE(second_approval_status, '') = ? "
            "ORDER BY created_at ASC",
            (approver, SECOND_PENDING),
        )

    # ---------------------------------------------------------------- 写
    @handle_exception(context="送复核")
    def request(
        self, sheet_number: str, first_approver: str, second_approver: str
    ) -> ServiceResult:
        """认领的管理员把单送去复核。"""
        row = self.sheets.get_by_number(sheet_number)
        if not row:
            return ServiceResult.fail(
                message=f"需求单不存在：{sheet_number}", error_code="SHEET_NOT_FOUND"
            )
        status = (row.get(RequirementSheetField.STATUS) or "").strip()
        if status not in OPEN_STATUSES:
            return ServiceResult.fail(
                message=f"需求单当前状态为「{status}」，已不在办，不用复核",
                error_code="INVALID_SHEET_STATE",
            )

        first = (first_approver or "").strip()
        second = (second_approver or "").strip()
        if not second:
            return ServiceResult.fail(
                message="请选择复核人：含管制化学品的单需要另一名管理员签字",
                error_code="SECOND_APPROVER_REQUIRED",
            )
        if second == first:
            return ServiceResult.fail(
                message="复核人不能是审批人本人", error_code="SAME_SECOND_APPROVER"
            )
        if second == (row.get(RequirementSheetField.REQUESTER) or "").strip():
            return ServiceResult.fail(
                message="复核人不能是申请人本人", error_code="APPLICANT_CANNOT_REVIEW"
            )
        if not self.is_admin(second):
            return ServiceResult.fail(
                message=f"复核人「{second}」不是管理员",
                error_code="INVALID_SECOND_APPROVER",
            )

        changed = self.sheets.update(
            row[RequirementSheetField.ID],
            {
                "second_approver": second,
                "second_approval_status": SECOND_PENDING,
                "second_approval_time": None,
                "second_approval_remark": None,
            },
        )
        if not changed:
            return ServiceResult.fail(
                message="送复核失败，请刷新后重试", error_code="WRITE_FAILED"
            )
        audit(
            first,
            "需求单送复核（含管控）",
            target_type="requirement",
            target_id=sheet_number,
            detail=f"复核人：{second}",
        )
        return ServiceResult.ok(
            data={"sheet_number": sheet_number, "second_approver": second},
            message=f"已送 {second} 复核；复核通过后才允许兑付发料",
        )

    @handle_exception(context="复核需求单")
    def approve(
        self, sheet_number: str, approver: str, remark: str = ""
    ) -> ServiceResult:
        """复核通过。"""
        row = self.sheets.get_by_number(sheet_number)
        if not row:
            return ServiceResult.fail(
                message=f"需求单不存在：{sheet_number}", error_code="SHEET_NOT_FOUND"
            )
        status = (row.get("second_approval_status") or "").strip()
        if status != SECOND_PENDING:
            return ServiceResult.fail(
                message="这张单当前不在等复核", error_code="INVALID_REVIEW_STATE"
            )
        assigned = (row.get("second_approver") or "").strip()
        if (approver or "").strip() != assigned:
            return ServiceResult.fail(
                message=f"这张单指定由「{assigned or '—'}」复核",
                error_code="NOT_SECOND_APPROVER",
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        changed = self.sheets.update(
            row[RequirementSheetField.ID],
            {
                "second_approval_status": SECOND_APPROVED,
                "second_approval_time": now,
                "second_approval_remark": remark or "",
            },
        )
        if not changed:
            return ServiceResult.fail(message="复核失败，请刷新后重试", error_code="WRITE_FAILED")
        audit(
            approver,
            "需求单复核通过（含管控）",
            target_type="requirement",
            target_id=sheet_number,
            detail=remark or "",
        )
        return ServiceResult.ok(
            data={"sheet_number": sheet_number},
            message="复核通过：现在可以兑付发料",
        )

    def consume(self, sheet_id: int) -> None:
        """兑付成功后作废本轮回合。

        不清 ``second_approver``：它是「上一双看过的眼睛」的留痕，排查时要看。
        """
        try:
            self.sheets.update(sheet_id, {"second_approval_status": ""})
        except Exception as exc:  # pragma: no cover - 作废失败不该回滚已发的料
            logger.warning(f"作废复核状态失败（sheet_id={sheet_id}）：{exc}")


requirement_review_service = RequirementReviewService()

__all__ = [
    "RequirementReviewService",
    "requirement_review_service",
    "OPEN_STATUSES",
]
