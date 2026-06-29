"""试剂归还业务服务

提供试剂归还的核心业务逻辑，包括归还记录创建、库存更新等功能。

使用面向对象设计，所有业务方法封装在 ReturnService 类中。
"""
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.return_record_service import return_record_service
from services.core.borrow_record_service import borrow_record_service
from business.expiry_service import expiry_service
from models.core.return_record import ReturnRecord
from utils.id_generator import id_generator
from utils.field_mapper import ReturnRecordField, ReagentBottleField, BorrowRecordField
from utils.error_handler import logger, ServiceResult, handle_exception
from datetime import datetime
from typing import Optional, List


class ReturnService:
    """试剂归还业务服务类

    封装所有试剂归还相关的业务逻辑，包括：
    - 试剂归还核心业务
    - 批量归还业务
    - 归还记录查询
    - 用户归还记录查询

    Attributes:
        bottle_service: 试剂瓶服务实例
        return_record_service: 归还记录服务实例
        borrow_record_service: 领用记录服务实例
        id_gen: 编号生成器实例
    """

    def __init__(self):
        """初始化归还服务"""
        self.bottle_service = reagent_bottle_service
        self.return_record_service = return_record_service
        self.borrow_record_service = borrow_record_service
        self.id_gen = id_generator

    @handle_exception(context="试剂归还")
    def reagent_return(
        self,
        bottle_number: str,
        return_user: str,
        remaining_qty: float
    ) -> ServiceResult:
        """试剂归还核心业务逻辑

        执行完整的试剂归还流程，包括试剂瓶校验、归还记录创建、
        领用记录关联更新和试剂瓶库存更新。

        Args:
            bottle_number: 试剂瓶编号（格式如：202606290001）
            return_user: 归还人姓名
            remaining_qty: 归还时的剩余量

        Returns:
            ServiceResult: 归还结果，成功时 data 包含归还记录信息，
                          失败时包含错误信息
        """
        # 参数校验
        if not bottle_number or not isinstance(bottle_number, str) or not bottle_number.strip():
            logger.warning(
                "参数校验失败: 试剂瓶编号无效",
                bottle_number=bottle_number
            )
            return ServiceResult.fail(
                message="试剂瓶编号不能为空",
                error_code="INVALID_BOTTLE_NUMBER"
            )

        if not return_user or not isinstance(return_user, str) or not return_user.strip():
            logger.warning(
                "参数校验失败: 归还人不能为空",
                return_user=return_user
            )
            return ServiceResult.fail(
                message="归还人不能为空",
                error_code="EMPTY_RETURN_USER"
            )

        if not isinstance(remaining_qty, (int, float)) or remaining_qty < 0:
            logger.warning(
                "参数校验失败: 剩余量不能为负数",
                remaining_qty=remaining_qty
            )
            return ServiceResult.fail(
                message="剩余量不能为负数",
                error_code="INVALID_REMAINING_QTY"
            )

        # 1. 查询试剂瓶
        bottle = self.bottle_service.get_by_bottle_number(bottle_number)
        if not bottle:
            logger.warning(
                "试剂瓶不存在",
                bottle_number=bottle_number
            )
            return ServiceResult.fail(
                message="未找到该试剂瓶",
                error_code="BOTTLE_NOT_FOUND"
            )

        # 2. 查找对应的领用记录（最近一条领用记录）
        borrow_records = self.borrow_record_service.get_by_bottle_number(bottle_number)
        linked_borrow_record_id = None
        linked_borrow_record_num = None

        # 找到最近一条领用记录（按领用时间倒序）
        if borrow_records:
            sorted_records = sorted(
                borrow_records,
                key=lambda x: getattr(x, BorrowRecordField.BORROW_TIME, "") or "",
                reverse=True
            )
            if sorted_records:
                latest_borrow = sorted_records[0]
                linked_borrow_record_id = latest_borrow.id
                linked_borrow_record_num = getattr(latest_borrow, BorrowRecordField.RECORD_NUMBER, None)
                logger.info(
                    "找到关联领用记录",
                    bottle_number=bottle_number,
                    borrow_record_number=linked_borrow_record_num
                )

        # 3. 生成归还记录编号
        return_num = self.id_gen.generate_return_record_number()

        # 4. 获取当前时间字符串
        current_time = datetime.now().strftime("%Y/%m/%d %H:%M")

        # 5. 创建归还记录数据
        return_data = {
            ReturnRecordField.RETURN_NUMBER: return_num,
            ReturnRecordField.BOTTLE_NUMBER: bottle_number,
            ReturnRecordField.RETURN_USER: return_user,
            ReturnRecordField.RETURN_TIME: current_time,
            ReturnRecordField.REMAINING_QUANTITY: remaining_qty,
            ReturnRecordField.LAST_UPDATE_TIME: current_time,
            ReturnRecordField.MODIFIER: return_user
        }

        # 添加关联借出记录号（如果存在）
        if linked_borrow_record_num:
            return_data[ReturnRecordField.LINKED_BORROW_RECORD_NUMBER] = linked_borrow_record_num

        logger.info(
            "尝试创建归还记录",
            return_number=return_num,
            bottle_number=bottle_number,
            return_user=return_user,
            remaining_qty=remaining_qty
        )

        # 6. 创建归还记录
        rid = self.return_record_service.create(return_data)
        logger.info(
            "归还记录创建结果",
            record_id=rid,
            return_number=return_num
        )

        if not rid:
            logger.error(
                "创建归还记录失败",
                return_number=return_num,
                bottle_number=bottle_number
            )
            return ServiceResult.fail(
                message="创建归还记录失败",
                error_code="CREATE_RETURN_RECORD_FAILED"
            )

        # 7. 更新领用记录中的关联归还记录号
        if linked_borrow_record_id:
            borrow_update_data = {
                BorrowRecordField.LINKED_RETURN_RECORD_NUMBER: return_num,
                BorrowRecordField.LAST_UPDATE_TIME: current_time,
                BorrowRecordField.MODIFIER: return_user
            }
            logger.info(
                "更新领用记录关联字段",
                borrow_record_id=linked_borrow_record_id,
                return_number=return_num
            )
            try:
                self.borrow_record_service.update(linked_borrow_record_id, borrow_update_data)
                logger.info(
                    "领用记录更新成功",
                    borrow_record_id=linked_borrow_record_id
                )
            except Exception as e:
                logger.warning(
                    "更新领用记录失败（可能记录已删除）",
                    borrow_record_id=linked_borrow_record_id,
                    error=str(e)
                )

        # 8. 更新试剂瓶信息
        bottle_id = getattr(bottle, ReagentBottleField.ID, None)
        borrowable_flag = "可借" if remaining_qty > 0 else "耗尽"
        borrowable_check = remaining_qty > 0

        updates = {
            ReagentBottleField.REMAINING_QUANTITY: remaining_qty,
            ReagentBottleField.LAST_RETURN_TIME: current_time,
            ReagentBottleField.LAST_RETURN_RECORD_NO: return_num,
            ReagentBottleField.BORROWABLE_FLAG: borrowable_flag,
            ReagentBottleField.BORROWABLE_CHECK: borrowable_check
        }
        self.bottle_service.update(bottle_id, updates)

        logger.info(
            "试剂瓶信息更新成功",
            bottle_number=bottle_number,
            remaining_qty=remaining_qty,
            borrowable_flag=borrowable_flag
        )

        # 9. 同步过期状态
        try:
            updated_bottle = self.bottle_service.get_by_bottle_number(bottle_number)
            if updated_bottle:
                expiry_service.check_and_update(updated_bottle)
        except Exception as e:
            logger.warning(
                "同步过期状态失败",
                bottle_number=bottle_number,
                exception=e,
            )

        # 10. 构造返回结果
        result_data = {
            "record_id": rid,
            "return_number": return_num,
            "bottle_number": bottle_number,
            "return_user": return_user,
            "remaining_qty": remaining_qty,
            "return_time": current_time,
            "linked_borrow_record_num": linked_borrow_record_num,
            "borrowable_flag": borrowable_flag
        }

        logger.info(
            "试剂归还成功",
            return_number=return_num,
            bottle_number=bottle_number,
            return_user=return_user
        )

        return ServiceResult.ok(data=result_data, message="归还成功！")

    @handle_exception(context="批量归还")
    def batch_return(self, return_list: list) -> ServiceResult:
        """批量归还业务逻辑

        批量处理试剂归还，统计成功和失败数量及失败详情。

        Args:
            return_list: 归还列表，每个元素为dict，包含bottle_number、
                        return_user、remaining_qty等字段

        Returns:
            ServiceResult: 批量归还结果，data 包含 success_count、fail_count、
                          fail_details 三个字段
        """
        # 参数校验
        if not isinstance(return_list, list):
            logger.warning(
                "参数校验失败: 归还列表类型无效",
                return_list_type=type(return_list).__name__
            )
            return ServiceResult.fail(
                message="归还列表必须为列表类型",
                error_code="INVALID_RETURN_LIST_TYPE"
            )

        success_count = 0
        fail_count = 0
        fail_details = []

        for item in return_list:
            bottle_number = item.get("bottle_number", "")
            return_user = item.get("return_user", "")
            remaining_qty = item.get("remaining_qty", 0.0)

            result = self.reagent_return(bottle_number, return_user, remaining_qty)

            if result.success:
                success_count += 1
            else:
                fail_count += 1
                fail_details.append({
                    "bottle_number": bottle_number,
                    "error": result.message,
                    "error_code": result.error_code
                })

        result_data = {
            "success_count": success_count,
            "fail_count": fail_count,
            "fail_details": fail_details
        }

        logger.info(
            "批量归还完成",
            total=len(return_list),
            success_count=success_count,
            fail_count=fail_count
        )

        message = f"批量归还完成：成功 {success_count} 条，失败 {fail_count} 条"
        return ServiceResult.ok(data=result_data, message=message)

    @handle_exception(context="查询归还记录")
    def get_return_record(self, record_id: str) -> ServiceResult:
        """根据记录ID查询归还记录

        Args:
            record_id: 归还记录ID

        Returns:
            ServiceResult: 查询结果，成功时 data 为 ReturnRecord 对象，
                          失败时包含错误信息
        """
        # 参数校验
        if not record_id or not isinstance(record_id, str):
            logger.warning(
                "参数校验失败: 记录ID无效",
                record_id=record_id
            )
            return ServiceResult.fail(
                message="记录ID不能为空",
                error_code="EMPTY_RECORD_ID"
            )

        record = self.return_record_service.get_by_id(record_id)
        if not record:
            logger.warning(
                "归还记录不存在",
                record_id=record_id
            )
            return ServiceResult.fail(
                message="未找到该归还记录",
                error_code="RECORD_NOT_FOUND"
            )

        logger.info(
            "查询归还记录成功",
            record_id=record_id,
            return_number=getattr(record, ReturnRecordField.RETURN_NUMBER, None)
        )

        return ServiceResult.ok(data=record, message="查询成功")

    @handle_exception(context="查询用户归还记录")
    def get_return_records_by_user(self, user: str) -> ServiceResult:
        """查询指定用户的所有归还记录

        Args:
            user: 用户姓名

        Returns:
            ServiceResult: 查询结果，成功时 data 为 ReturnRecord 对象列表，
                          失败时包含错误信息
        """
        # 参数校验
        if not user or not isinstance(user, str) or not user.strip():
            logger.warning(
                "参数校验失败: 用户姓名不能为空",
                user=user
            )
            return ServiceResult.fail(
                message="用户姓名不能为空",
                error_code="EMPTY_USER"
            )

        records = self.return_record_service.get_by_user(user)

        logger.info(
            "查询用户归还记录成功",
            user=user,
            count=len(records)
        )

        return ServiceResult.ok(data=records, message=f"查询到 {len(records)} 条记录")


# ============================================================================
# 全局单例实例
# ============================================================================

return_service = ReturnService()
