"""看板统计业务服务

提供试剂库的各种统计功能，包括库存统计、领用统计、归还统计等。

使用 DashboardService 类封装所有统计相关业务方法，
使用字段常量替代硬编码字段名，使用 logger 和 ServiceResult 统一错误处理。
"""
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.borrow_record_service import borrow_record_service
from services.core.return_record_service import return_record_service
from models.core.reagent_bottle import ReagentBottle
from models.core.borrow_record import BorrowRecord
from models.core.return_record import ReturnRecord
from utils.field_mapper import (
    ReagentBottleField,
    BorrowRecordField,
    ReturnRecordField,
)
from utils.error_handler import logger, ServiceResult, handle_exception
from typing import Dict, Any, List


class DashboardService:
    """看板统计服务类

    封装所有统计相关的业务方法，包括：
    - 库存统计
    - 领用统计
    - 归还统计
    - 供应商统计
    - 存储位置统计
    - 待审批数量统计

    Attributes:
        bottle_service: 试剂瓶服务实例
        borrow_service: 领用记录服务实例
        return_service: 归还记录服务实例
    """

    def __init__(self):
        """初始化看板统计服务

        注入所有依赖的服务实例，便于测试和维护。
        """
        self.bottle_service = reagent_bottle_service
        self.borrow_service = borrow_record_service
        self.return_service = return_record_service
        logger.info("DashboardService 初始化完成")

    # ------------------------------------------------------------------
    # 1. 库存统计
    # ------------------------------------------------------------------

    @handle_exception(context="库存统计")
    def get_inventory_stats(self) -> ServiceResult[Dict[str, Any]]:
        """获取库存统计数据

        统计试剂瓶总数、可借数量、耗尽数量、已借出数量和总剩余量。

        Returns:
            ServiceResult[Dict[str, Any]] - 包含库存统计信息的字典：
            - total_bottles: 试剂瓶总数
            - borrowable: 可借数量
            - exhausted: 耗尽数量
            - borrowed: 已借出数量
            - total_quantity: 总剩余量
        """
        try:
            bottles: List[ReagentBottle] = self.bottle_service.get_all_parsed()

            total = len(bottles)
            borrowable = 0
            exhausted = 0
            borrowed = 0
            total_quantity = 0.0

            for bottle in bottles:
                status = getattr(bottle, ReagentBottleField.BORROWABLE_FLAG, "")
                qty = getattr(bottle, ReagentBottleField.REMAINING_QUANTITY, 0.0) or 0.0

                if status == "可借":
                    borrowable += 1
                elif status == "耗尽":
                    exhausted += 1
                elif status == "已借出":
                    borrowed += 1

                if qty:
                    total_quantity += qty

            stats = {
                "total_bottles": total,
                "borrowable": borrowable,
                "exhausted": exhausted,
                "borrowed": borrowed,
                "total_quantity": round(total_quantity, 2),
            }

            logger.info(
                "库存统计完成",
                total_bottles=total,
                borrowable=borrowable,
                exhausted=exhausted,
                borrowed=borrowed,
                total_quantity=round(total_quantity, 2),
            )

            return ServiceResult.ok(data=stats, message="库存统计完成")

        except Exception as e:
            logger.error("库存统计失败", exception=e)
            return ServiceResult.fail(
                message=f"库存统计失败: {str(e)}",
                error_code="INVENTORY_STATS_ERROR",
            )

    # ------------------------------------------------------------------
    # 2. 领用统计
    # ------------------------------------------------------------------

    @handle_exception(context="领用统计")
    def get_borrow_stats(self) -> ServiceResult[Dict[str, Any]]:
        """获取领用统计数据

        统计领用总次数和按领用人的领用次数。

        Returns:
            ServiceResult[Dict[str, Any]] - 包含领用统计信息的字典：
            - total_borrows: 领用总次数
            - user_stats: 按领用人统计的字典
        """
        try:
            records: List[BorrowRecord] = self.borrow_service.get_all_parsed()

            total_borrows = len(records)

            # 按领用人统计
            user_stats: Dict[str, int] = {}
            for record in records:
                user = getattr(record, BorrowRecordField.USER, "未知") or "未知"
                user_stats[user] = user_stats.get(user, 0) + 1

            stats = {
                "total_borrows": total_borrows,
                "user_stats": user_stats,
            }

            logger.info(
                "领用统计完成",
                total_borrows=total_borrows,
                user_count=len(user_stats),
            )

            return ServiceResult.ok(data=stats, message="领用统计完成")

        except Exception as e:
            logger.error("领用统计失败", exception=e)
            return ServiceResult.fail(
                message=f"领用统计失败: {str(e)}",
                error_code="BORROW_STATS_ERROR",
            )

    # ------------------------------------------------------------------
    # 3. 归还统计
    # ------------------------------------------------------------------

    @handle_exception(context="归还统计")
    def get_return_stats(self) -> ServiceResult[Dict[str, Any]]:
        """获取归还统计数据

        统计归还总次数和按归还人的归还次数。

        Returns:
            ServiceResult[Dict[str, Any]] - 包含归还统计信息的字典：
            - total_returns: 归还总次数
            - user_stats: 按归还人统计的字典
        """
        try:
            records: List[ReturnRecord] = self.return_service.get_all_parsed()

            total_returns = len(records)

            # 按归还人统计
            user_stats: Dict[str, int] = {}
            for record in records:
                user = getattr(record, ReturnRecordField.RETURN_USER, "未知") or "未知"
                user_stats[user] = user_stats.get(user, 0) + 1

            stats = {
                "total_returns": total_returns,
                "user_stats": user_stats,
            }

            logger.info(
                "归还统计完成",
                total_returns=total_returns,
                user_count=len(user_stats),
            )

            return ServiceResult.ok(data=stats, message="归还统计完成")

        except Exception as e:
            logger.error("归还统计失败", exception=e)
            return ServiceResult.fail(
                message=f"归还统计失败: {str(e)}",
                error_code="RETURN_STATS_ERROR",
            )

    # ------------------------------------------------------------------
    # 4. 供应商统计
    # ------------------------------------------------------------------

    @handle_exception(context="供应商统计")
    def get_supplier_stats(self) -> ServiceResult[Dict[str, int]]:
        """获取供应商统计数据

        按供应商统计试剂瓶数量。

        Returns:
            ServiceResult[Dict[str, int]] - 按供应商统计试剂瓶数量的字典
        """
        try:
            bottles: List[ReagentBottle] = self.bottle_service.get_all_parsed()

            supplier_stats: Dict[str, int] = {}
            for bottle in bottles:
                supplier = getattr(bottle, ReagentBottleField.SUPPLIER, "未知") or "未知"
                supplier_stats[supplier] = supplier_stats.get(supplier, 0) + 1

            logger.info(
                "供应商统计完成",
                supplier_count=len(supplier_stats),
                total_bottles=len(bottles),
            )

            return ServiceResult.ok(data=supplier_stats, message="供应商统计完成")

        except Exception as e:
            logger.error("供应商统计失败", exception=e)
            return ServiceResult.fail(
                message=f"供应商统计失败: {str(e)}",
                error_code="SUPPLIER_STATS_ERROR",
            )

    # ------------------------------------------------------------------
    # 5. 存储位置统计
    # ------------------------------------------------------------------

    @handle_exception(context="存储位置统计")
    def get_storage_location_stats(self) -> ServiceResult[Dict[str, int]]:
        """获取存储位置统计数据

        按存储位置统计试剂瓶数量。

        Returns:
            ServiceResult[Dict[str, int]] - 按存储位置统计试剂瓶数量的字典
        """
        try:
            bottles: List[ReagentBottle] = self.bottle_service.get_all_parsed()

            location_stats: Dict[str, int] = {}
            for bottle in bottles:
                location = getattr(bottle, ReagentBottleField.STORAGE_LOCATION, "未知") or "未知"
                location_stats[location] = location_stats.get(location, 0) + 1

            logger.info(
                "存储位置统计完成",
                location_count=len(location_stats),
                total_bottles=len(bottles),
            )

            return ServiceResult.ok(data=location_stats, message="存储位置统计完成")

        except Exception as e:
            logger.error("存储位置统计失败", exception=e)
            return ServiceResult.fail(
                message=f"存储位置统计失败: {str(e)}",
                error_code="STORAGE_LOCATION_STATS_ERROR",
            )

    # ------------------------------------------------------------------
    # 6. 待审批数量统计
    # ------------------------------------------------------------------

    @handle_exception(context="待审批数量统计")
    def get_pending_approval_count(self) -> ServiceResult[int]:
        """获取待审批数量

        统计待审批的领用记录数量。

        Returns:
            ServiceResult[int] - 待审批的领用记录数量
        """
        try:
            pending_records: List[BorrowRecord] = self.borrow_service.get_pending_approvals()
            count = len(pending_records)

            logger.info("待审批数量统计完成", pending_count=count)

            return ServiceResult.ok(data=count, message="待审批数量统计完成")

        except Exception as e:
            logger.error("待审批数量统计失败", exception=e)
            return ServiceResult.fail(
                message=f"待审批数量统计失败: {str(e)}",
                error_code="PENDING_APPROVAL_STATS_ERROR",
            )

    # ------------------------------------------------------------------
    # 7. 综合统计（一次性获取所有统计数据）
    # ------------------------------------------------------------------

    @handle_exception(context="综合统计")
    def get_all_stats(self) -> ServiceResult[Dict[str, Any]]:
        """一次性获取所有统计数据

        整合库存、领用、归还、供应商、存储位置和待审批等所有统计数据。

        Returns:
            ServiceResult[Dict[str, Any]] - 包含所有统计信息的字典
        """
        try:
            logger.info("开始获取综合统计数据")

            inventory_result = self.get_inventory_stats()
            borrow_result = self.get_borrow_stats()
            return_result = self.get_return_stats()
            supplier_result = self.get_supplier_stats()
            location_result = self.get_storage_location_stats()
            pending_result = self.get_pending_approval_count()

            all_stats = {
                "inventory": inventory_result.data if inventory_result.is_success() else {},
                "borrow": borrow_result.data if borrow_result.is_success() else {},
                "return": return_result.data if return_result.is_success() else {},
                "supplier": supplier_result.data if supplier_result.is_success() else {},
                "storage_location": location_result.data if location_result.is_success() else {},
                "pending_approval": pending_result.data if pending_result.is_success() else 0,
            }

            logger.info("综合统计数据获取完成")

            return ServiceResult.ok(data=all_stats, message="综合统计完成")

        except Exception as e:
            logger.error("综合统计失败", exception=e)
            return ServiceResult.fail(
                message=f"综合统计失败: {str(e)}",
                error_code="ALL_STATS_ERROR",
            )


# ============================================================================
# 全局单例实例
# ============================================================================

dashboard_service = DashboardService()


# ============================================================================
# 向后兼容的函数别名（保持原函数名和返回类型不变）
# ============================================================================

def get_inventory_stats() -> Dict[str, Any]:
    """获取库存统计数据（向后兼容）

    Returns:
        包含库存统计信息的字典：
        - total_bottles: 试剂瓶总数
        - borrowable: 可借数量
        - exhausted: 耗尽数量
        - borrowed: 已借出数量
        - total_quantity: 总剩余量
    """
    result = dashboard_service.get_inventory_stats()
    if result.is_success():
        return result.data
    return {
        "total_bottles": 0,
        "borrowable": 0,
        "exhausted": 0,
        "borrowed": 0,
        "total_quantity": 0.0,
    }


def get_borrow_stats() -> Dict[str, Any]:
    """获取领用统计数据（向后兼容）

    Returns:
        包含领用统计信息的字典：
        - total_borrows: 领用总次数
        - user_stats: 按领用人统计的字典
    """
    result = dashboard_service.get_borrow_stats()
    if result.is_success():
        return result.data
    return {"total_borrows": 0, "user_stats": {}}


def get_return_stats() -> Dict[str, Any]:
    """获取归还统计数据（向后兼容）

    Returns:
        包含归还统计信息的字典：
        - total_returns: 归还总次数
        - user_stats: 按归还人统计的字典
    """
    result = dashboard_service.get_return_stats()
    if result.is_success():
        return result.data
    return {"total_returns": 0, "user_stats": {}}


def get_supplier_stats() -> Dict[str, int]:
    """获取供应商统计数据（向后兼容）

    Returns:
        按供应商统计试剂瓶数量的字典
    """
    result = dashboard_service.get_supplier_stats()
    if result.is_success():
        return result.data
    return {}


def get_storage_location_stats() -> Dict[str, int]:
    """获取存储位置统计数据（向后兼容）

    Returns:
        按存储位置统计试剂瓶数量的字典
    """
    result = dashboard_service.get_storage_location_stats()
    if result.is_success():
        return result.data
    return {}


def get_pending_approval_count() -> int:
    """获取待审批数量（向后兼容）

    Returns:
        待审批的领用记录数量
    """
    result = dashboard_service.get_pending_approval_count()
    if result.is_success():
        return result.data
    return 0
