"""管理人（保管权）业务服务

负责试剂瓶「当前管理人」的管理权流转：
- 借出 / 归还 **不** 改变管理人（借还是纯借用）；
- 管理人要变更时，通过本服务的 `transfer` 进行显式流转，并写入变更记录。

对应数据表：reagent_bottle.manager、manager_change_log
"""
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.manager_change_log_service import manager_change_log_service
from services.base.person_service import person_service
from utils.field_mapper import ReagentBottleField, ManagerChangeLogField
from utils.error_handler import logger, ServiceResult, handle_exception
from utils.audit import audit
from db.database import db
from datetime import datetime
from typing import Optional, List

# 变更原因
REASON_MANUAL = "手工流转"        # 管理员主动把试剂流转给同事
REASON_ALLOCATION = "调配借出"    # 需求调配借出后形成的新保管（预留）
REASON_RETURN = "归还回转"        # 归还时转回原管理人（预留）


class ManagerService:
    """管理人（保管权）业务服务类"""

    def __init__(self):
        self.bottle_service = reagent_bottle_service
        self.log_service = manager_change_log_service
        self.person_service = person_service

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_super_admin_name(self) -> Optional[str]:
        """获取超级管理员姓名（无管理人的试剂瓶默认归属超管）"""
        for person in self.person_service.get_by_role("super_admin"):
            if person.name:
                return person.name
        return None

    def resolve_manager(self, manager: Optional[str]) -> Optional[str]:
        """解析有效管理人：为空时归属超级管理员"""
        if manager and str(manager).strip():
            return manager
        return self.get_super_admin_name()

    @handle_exception(context="获取管理人候选")
    def get_candidates(self) -> ServiceResult[List[str]]:
        """获取管理权流转的目标候选人（全体人员）

        流转是「转给同事」，同事可能并非管理员，故候选人取全体人员。

        Returns:
            ServiceResult[List[str]] - 去重排序后的姓名列表
        """
        names = sorted({p.name for p in self.person_service.get_all_persons() if p.name})
        logger.info("获取管理人候选完成", count=len(names))
        return ServiceResult.ok(data=names)

    @handle_exception(context="查询管理人变更历史")
    def get_history(self, bottle_number: str) -> ServiceResult[List]:
        """查询某试剂瓶的管理人变更历史（最新在前）"""
        if not bottle_number or not str(bottle_number).strip():
            return ServiceResult.fail(
                message="试剂瓶编号不能为空",
                error_code="INVALID_BOTTLE_NUMBER"
            )
        logs = self.log_service.get_by_bottle(str(bottle_number).strip())
        return ServiceResult.ok(data=logs, message=f"共 {len(logs)} 条变更记录")

    # ------------------------------------------------------------------
    # 管理权流转
    # ------------------------------------------------------------------

    @handle_exception(context="管理权流转")
    def transfer(
        self,
        bottle_number: str,
        new_manager: str,
        operator: str,
        reason: str = REASON_MANUAL,
        remark: Optional[str] = None,
        ref_type: Optional[str] = None,
        ref_id: Optional[str] = None,
    ) -> ServiceResult:
        """将某试剂瓶的管理权流转给新管理人

        Args:
            bottle_number: 试剂瓶编号
            new_manager: 新管理人姓名
            operator: 操作人姓名
            reason: 变更原因
            remark: 备注
            ref_type: 关联单据类型（可选）
            ref_id: 关联单据ID（可选）

        Returns:
            ServiceResult - 成功时 data 含 old_manager / new_manager
        """
        if not bottle_number or not str(bottle_number).strip():
            return ServiceResult.fail(
                message="试剂瓶编号不能为空",
                error_code="INVALID_BOTTLE_NUMBER"
            )
        if not new_manager or not str(new_manager).strip():
            return ServiceResult.fail(
                message="新管理人不能为空",
                error_code="EMPTY_NEW_MANAGER"
            )

        bottle_number = str(bottle_number).strip()
        new_manager = str(new_manager).strip()

        bottle = self.bottle_service.get_by_bottle_number(bottle_number)
        if not bottle:
            return ServiceResult.fail(
                message="未找到该试剂瓶",
                error_code="BOTTLE_NOT_FOUND"
            )

        old_manager = getattr(bottle, ReagentBottleField.MANAGER, None)
        if old_manager == new_manager:
            return ServiceResult.fail(
                message=f"该试剂瓶的管理人已是「{new_manager}」，无需流转",
                error_code="SAME_MANAGER"
            )

        changed_at = datetime.now().strftime("%Y/%m/%d %H:%M")

        with db.transaction():
            updated = self.bottle_service.update(
                bottle.id, {ReagentBottleField.MANAGER: new_manager}
            )
            if not updated:
                raise RuntimeError("更新试剂瓶管理人失败，已回滚")

            self.log_service.create({
                ManagerChangeLogField.BOTTLE_NUMBER: bottle_number,
                ManagerChangeLogField.REAGENT_NAME: getattr(
                    bottle, ReagentBottleField.REAGENT_NAME, None
                ),
                ManagerChangeLogField.OLD_MANAGER: old_manager,
                ManagerChangeLogField.NEW_MANAGER: new_manager,
                ManagerChangeLogField.REASON: reason,
                ManagerChangeLogField.REF_TYPE: ref_type,
                ManagerChangeLogField.REF_ID: (
                    str(ref_id) if ref_id is not None else None
                ),
                ManagerChangeLogField.REMARK: remark,
                ManagerChangeLogField.OPERATOR: operator,
                ManagerChangeLogField.CHANGED_AT: changed_at,
            })

        logger.info(
            "管理权流转成功",
            bottle_number=bottle_number,
            old_manager=old_manager,
            new_manager=new_manager,
            operator=operator,
        )
        audit(
            operator,
            "管理权流转",
            target_type="bottle",
            target_id=bottle_number,
            detail=f"管理人 {old_manager or '—'} → {new_manager}（{reason}）",
        )
        return ServiceResult.ok(
            data={
                "bottle_number": bottle_number,
                "old_manager": old_manager,
                "new_manager": new_manager,
                "changed_at": changed_at,
            },
            message=f"已将该试剂的管理权流转给「{new_manager}」",
        )


    @handle_exception(context="批量管理权流转")
    def transfer_batch(
        self,
        bottle_numbers: List[str],
        new_manager: str,
        operator: str,
        reason: str = REASON_MANUAL,
        remark: Optional[str] = None,
    ) -> ServiceResult:
        """将多瓶试剂的管理权批量流转给新管理人（购物车 / 多选模式）

        Args:
            bottle_numbers: 试剂瓶编号列表
            new_manager: 新管理人姓名
            operator: 操作人姓名
            reason: 变更原因
            remark: 备注

        Returns:
            ServiceResult - data 含 succeeded / failed 列表
        """
        if not bottle_numbers:
            return ServiceResult.fail(
                message="请先勾选要流转的试剂瓶",
                error_code="EMPTY_SELECTION"
            )
        if not new_manager or not str(new_manager).strip():
            return ServiceResult.fail(
                message="新管理人不能为空",
                error_code="EMPTY_NEW_MANAGER"
            )

        succeeded, failed = [], []
        for bottle_number in bottle_numbers:
            result = self.transfer(
                bottle_number, new_manager, operator, reason=reason, remark=remark
            )
            if result.is_success():
                succeeded.append(bottle_number)
            else:
                failed.append(f"{bottle_number}: {result.message}")

        if not succeeded:
            return ServiceResult.fail(
                message="全部流转失败：" + "；".join(failed),
                error_code="TRANSFER_ALL_FAILED",
                data={"succeeded": succeeded, "failed": failed},
            )

        message = f"✅ 已将 {len(succeeded)} 瓶试剂的管理权流转给「{new_manager}」"
        if failed:
            message += f"；失败 {len(failed)} 瓶：{'；'.join(failed)}"
        return ServiceResult.ok(
            data={"succeeded": succeeded, "failed": failed},
            message=message,
        )


# ============================================================================
# 全局单例实例
# ============================================================================

manager_service = ManagerService()
