"""试剂领用业务服务

提供试剂领用的核心业务逻辑，包括试剂瓶校验、管控试剂检查、库存更新等功能。

使用面向对象设计，所有业务方法封装在 BorrowService 类中。
"""
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.borrow_record_service import borrow_record_service
from services.base.controlled_list_service import controlled_list_service
from business.expiry_service import expiry_service
from models.core.borrow_record import BorrowRecord
from utils.id_generator import id_generator
from utils.field_mapper import BorrowRecordField, ReagentBottleField
from utils.error_handler import logger, ServiceResult, handle_exception
from datetime import datetime
from typing import Optional, List


class BorrowService:
    """试剂领用业务服务类

    封装所有试剂领用相关的业务逻辑，包括：
    - 试剂领用核心业务
    - 领用记录查询
    - 用户领用记录查询

    Attributes:
        bottle_service: 试剂瓶服务实例
        record_service: 领用记录服务实例
        controlled_service: 管控化学品服务实例
        id_gen: 编号生成器实例
    """

    def __init__(self):
        """初始化领用服务"""
        self.bottle_service = reagent_bottle_service
        self.record_service = borrow_record_service
        self.controlled_service = controlled_list_service
        self.id_gen = id_generator

    @handle_exception(context="试剂领用")
    def reagent_borrow(
        self,
        bottle_number: str,
        user: str,
        borrow_qty: float
    ) -> ServiceResult:
        """试剂领用核心业务逻辑

        执行完整的试剂领用流程，包括试剂瓶校验、管控试剂检查、
        领用记录创建和库存更新。

        Args:
            bottle_number: 试剂瓶编号（格式如：202606290001）
            user: 领用人姓名
            borrow_qty: 领用数量

        Returns:
            ServiceResult: 领用结果，成功时 data 包含领用记录信息，
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

        if not user or not isinstance(user, str) or not user.strip():
            logger.warning(
                "参数校验失败: 领用人不能为空",
                user=user
            )
            return ServiceResult.fail(
                message="领用人不能为空",
                error_code="EMPTY_USER"
            )

        if not isinstance(borrow_qty, (int, float)) or borrow_qty <= 0:
            logger.warning(
                "参数校验失败: 领用数量无效",
                borrow_qty=borrow_qty
            )
            return ServiceResult.fail(
                message="领用数量必须大于0",
                error_code="INVALID_BORROW_QTY"
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

        # 2. 校验试剂瓶状态
        borrowable_flag = getattr(bottle, ReagentBottleField.BORROWABLE_FLAG, None)
        if borrowable_flag != "可借":
            logger.warning(
                "试剂瓶不可借出",
                bottle_number=bottle_number,
                status=borrowable_flag
            )
            return ServiceResult.fail(
                message=f"该试剂当前状态为「{borrowable_flag}」，不可借出",
                error_code="BOTTLE_NOT_BORROWABLE"
            )

        # 2.1 校验试剂是否已过期
        expired_flag = getattr(bottle, ReagentBottleField.EXPIRED_FLAG, None)
        if expired_flag == "已过期":
            logger.warning(
                "试剂已过期，禁止借出",
                bottle_number=bottle_number,
                expired_flag=expired_flag
            )
            return ServiceResult.fail(
                message="该试剂已过期，禁止借出",
                error_code="REAGENT_EXPIRED"
            )

        # 3. 校验领用数量
        remaining_qty = getattr(bottle, ReagentBottleField.REMAINING_QUANTITY, None)
        if remaining_qty is None:
            logger.warning(
                "试剂剩余量未知",
                bottle_number=bottle_number
            )
            return ServiceResult.fail(
                message="试剂剩余量未知",
                error_code="UNKNOWN_REMAINING_QTY"
            )

        if borrow_qty > remaining_qty:
            logger.warning(
                "领用数量超过剩余量",
                bottle_number=bottle_number,
                borrow_qty=borrow_qty,
                remaining_qty=remaining_qty
            )
            return ServiceResult.fail(
                message=f"领用数量超过剩余量（当前剩余：{remaining_qty}g）",
                error_code="EXCEED_REMAINING_QTY"
            )

        # 4. 检查是否为管控试剂
        is_controlled = False
        controlled_type = None
        cas_number = getattr(bottle, ReagentBottleField.CAS_NUMBER, None)
        if cas_number:
            controlled_item = self.controlled_service.get_by_cas_number(cas_number)
            if controlled_item:
                is_controlled = True
                controlled_type = getattr(controlled_item, 'dangerous_type', None)
                logger.info(
                    "检测到管控试剂",
                    bottle_number=bottle_number,
                    cas_number=cas_number,
                    controlled_type=controlled_type
                )

        # 5. 创建领用记录前再次检查状态（防止并发问题）
        bottle_refresh = self.bottle_service.get_by_bottle_number(bottle_number)
        if bottle_refresh:
            refresh_flag = getattr(bottle_refresh, ReagentBottleField.BORROWABLE_FLAG, None)
            if refresh_flag != "可借":
                logger.warning(
                    "试剂已被其他用户领用",
                    bottle_number=bottle_number,
                    status=refresh_flag
                )
                return ServiceResult.fail(
                    message=f"该试剂已被其他用户领用，当前状态为「{refresh_flag}」",
                    error_code="BOTTLE_ALREADY_BORROWED"
                )

        # 6. 创建领用记录
        record_num = self.id_gen.generate_borrow_record_number()
        current_time = datetime.now().strftime("%Y/%m/%d %H:%M")

        borrow_data = {
            BorrowRecordField.RECORD_NUMBER: record_num,
            BorrowRecordField.BOTTLE_NUMBER: getattr(bottle, ReagentBottleField.BOTTLE_NUMBER),
            BorrowRecordField.USER: user,
            BorrowRecordField.BORROW_TIME: current_time
        }

        # 添加可选字段（从试剂瓶信息继承）
        reagent_name = getattr(bottle, ReagentBottleField.REAGENT_NAME, None)
        if reagent_name:
            borrow_data[BorrowRecordField.REAGENT_NAME] = reagent_name

        bottle_cas = getattr(bottle, ReagentBottleField.CAS_NUMBER, None)
        if bottle_cas:
            borrow_data[BorrowRecordField.CAS_NUMBER] = bottle_cas

        production_date = getattr(bottle, ReagentBottleField.PRODUCTION_DATE, None)
        if production_date:
            borrow_data[BorrowRecordField.PRODUCTION_DATE] = production_date

        logger.info(
            "尝试创建领用记录",
            record_number=record_num,
            bottle_number=bottle_number,
            user=user,
            borrow_qty=borrow_qty
        )

        # 创建领用记录
        rid = self.record_service.create(borrow_data)
        logger.info(
            "领用记录创建结果",
            record_id=rid,
            record_number=record_num
        )

        if not rid:
            logger.error(
                "创建领用记录失败",
                record_number=record_num,
                bottle_number=bottle_number
            )
            return ServiceResult.fail(
                message="创建领用记录失败",
                error_code="CREATE_RECORD_FAILED"
            )

        # 7. 更新试剂瓶库存和状态
        new_qty = remaining_qty - borrow_qty
        updates = {
            ReagentBottleField.REMAINING_QUANTITY: new_qty,
            ReagentBottleField.LAST_BORROW_TIME: current_time,
            ReagentBottleField.BORROWABLE_FLAG: "已借出",
            ReagentBottleField.BORROWABLE_CHECK: False
        }

        # 首次借出时写入启封日期（精确到小时），后续不再覆盖
        existing_unseal = getattr(bottle, ReagentBottleField.UNSEAL_DATE, None)
        if not existing_unseal:
            updates[ReagentBottleField.UNSEAL_DATE] = current_time
            logger.info(
                "首次借出，写入启封日期",
                bottle_number=bottle_number,
                unseal_date=current_time
            )
        self.bottle_service.update(bottle.id, updates)

        logger.info(
            "试剂瓶库存更新成功",
            bottle_number=bottle_number,
            old_qty=remaining_qty,
            new_qty=new_qty
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
            "record_number": record_num,
            "bottle_number": bottle_number,
            "user": user,
            "borrow_qty": borrow_qty,
            "remaining_qty": new_qty,
            "is_controlled": is_controlled,
            "controlled_type": controlled_type,
            "borrow_time": current_time
        }

        if is_controlled:
            message = f"领用成功！该试剂为管控化学品({controlled_type})，请及时补全审批手续"
        else:
            message = "领用成功！"

        logger.info(
            "试剂领用成功",
            record_number=record_num,
            bottle_number=bottle_number,
            user=user
        )

        return ServiceResult.ok(data=result_data, message=message)

    @handle_exception(context="查询领用记录")
    def get_borrow_record(self, record_id: str) -> ServiceResult:
        """根据记录ID查询领用记录

        Args:
            record_id: 领用记录ID

        Returns:
            ServiceResult: 查询结果，成功时 data 为 BorrowRecord 对象，
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

        record = self.record_service.get_by_id(record_id)
        if not record:
            logger.warning(
                "领用记录不存在",
                record_id=record_id
            )
            return ServiceResult.fail(
                message="未找到该领用记录",
                error_code="RECORD_NOT_FOUND"
            )

        logger.info(
            "查询领用记录成功",
            record_id=record_id,
            record_number=record.record_number
        )

        return ServiceResult.ok(data=record, message="查询成功")

    @handle_exception(context="查询用户领用记录")
    def get_borrow_records_by_user(self, user: str) -> ServiceResult:
        """查询指定用户的所有领用记录

        Args:
            user: 用户姓名

        Returns:
            ServiceResult: 查询结果，成功时 data 为 BorrowRecord 对象列表，
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

        records = self.record_service.get_by_user(user)

        logger.info(
            "查询用户领用记录成功",
            user=user,
            count=len(records)
        )

        return ServiceResult.ok(data=records, message=f"查询到 {len(records)} 条记录")

    @handle_exception(context="获取所有领用人列表")
    def get_all_borrow_users(self) -> ServiceResult:
        """获取所有领用人列表（去重排序）

        Returns:
            ServiceResult: 查询结果，成功时 data 为领用人姓名列表
        """
        records = self.record_service.get_all_parsed()
        user_set = set()
        for record in records:
            user = getattr(record, 'user', None)
            if user:
                user_set.add(user)

        user_list = sorted(user_set)

        logger.info(
            "获取所有领用人列表成功",
            user_count=len(user_list)
        )

        return ServiceResult.ok(data=user_list, message=f"共 {len(user_list)} 个领用人")

    @handle_exception(context="获取指定试剂瓶最新领用记录")
    def get_latest_borrow_record(self, bottle_number: str) -> ServiceResult:
        """获取指定试剂瓶的最新领用记录

        Args:
            bottle_number: 试剂瓶编号（格式如：202606290001）

        Returns:
            ServiceResult: 查询结果，成功时 data 为最新的 BorrowRecord 对象，
                          没有记录时 data 为 None
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

        records = self.record_service.get_by_bottle_number(bottle_number)

        if not records:
            logger.info(
                "试剂瓶无领用记录",
                bottle_number=bottle_number
            )
            return ServiceResult.ok(data=None, message="无领用记录")

        # 按领用时间倒序排序，取最新的
        sorted_records = sorted(
            records,
            key=lambda x: getattr(x, 'borrow_time', '') or '',
            reverse=True
        )

        latest = sorted_records[0]
        logger.info(
            "获取最新领用记录成功",
            bottle_number=bottle_number,
            user=getattr(latest, 'user', '')
        )

        return ServiceResult.ok(data=latest, message="查询成功")


# ============================================================================
# 全局单例实例
# ============================================================================

borrow_service = BorrowService()
