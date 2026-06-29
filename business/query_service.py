"""查询业务服务

提供试剂库的各种查询功能，包括多条件组合查询、历史记录查询等。

使用面向对象设计，所有查询方法封装在 QueryService 类中，
使用字段常量替代硬编码字段名，使用 logger 和 ServiceResult 统一错误处理。
"""
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.borrow_record_service import borrow_record_service
from services.core.return_record_service import return_record_service
from services.base.controlled_list_service import controlled_list_service
from models.core.reagent_bottle import ReagentBottle
from models.base.controlled_list import ControlledList
from utils.field_mapper import ReagentBottleField, BorrowRecordField, ReturnRecordField
from utils.error_handler import logger, ServiceResult, handle_exception
from typing import List, Optional, Dict, Any, Union


class QueryService:
    """查询业务服务类

    封装所有试剂查询相关的业务逻辑，包括：
    - 多条件组合查询试剂
    - 领用历史记录查询
    - 归还历史记录查询
    - 获取所有试剂瓶列表

    Attributes:
        bottle_service: 试剂瓶服务实例
        borrow_service: 领用记录服务实例
        return_service: 归还记录服务实例
    """

    def __init__(self):
        """初始化查询服务"""
        self.bottle_service = reagent_bottle_service
        self.borrow_service = borrow_record_service
        self.return_service = return_record_service
        self.controlled_service = controlled_list_service
        logger.info("QueryService 初始化完成")

    # ------------------------------------------------------------------
    # 1. 试剂查询
    # ------------------------------------------------------------------

    @handle_exception(context="多条件查询试剂")
    def search_reagents(
        self,
        bottle_number: Optional[str] = None,
        reagent_name: Optional[str] = None,
        cas_number: Optional[str] = None,
        supplier: Optional[str] = None,
        storage_location: Optional[str] = None,
        borrowable_only: bool = False
    ) -> ServiceResult[List[ReagentBottle]]:
        """多条件组合查询试剂（数据库层过滤）

        Args:
            bottle_number: 试剂瓶编号（精确匹配，格式如：202606290001）
            reagent_name: 试剂名称（模糊匹配）
            cas_number: CAS编号（精确匹配）
            supplier: 供应商（模糊匹配）
            storage_location: 存储位置（精确匹配）
            borrowable_only: 是否只显示可借试剂

        Returns:
            ServiceResult[List[ReagentBottle]]: 匹配的试剂瓶列表
        """
        # 参数校验
        if bottle_number is not None:
            if not isinstance(bottle_number, int) or bottle_number <= 0:
                logger.warning(
                    "参数校验失败: 试剂瓶编号无效",
                    bottle_number=bottle_number
                )
                return ServiceResult.fail(
                    message="试剂瓶编号必须为正整数",
                    error_code="INVALID_BOTTLE_NUMBER"
                )

        if reagent_name is not None and not isinstance(reagent_name, str):
            logger.warning(
                "参数校验失败: 试剂名称类型无效",
                reagent_name_type=type(reagent_name).__name__
            )
            return ServiceResult.fail(
                message="试剂名称必须为字符串类型",
                error_code="INVALID_REAGENT_NAME_TYPE"
            )

        if cas_number is not None and not isinstance(cas_number, str):
            logger.warning(
                "参数校验失败: CAS编号类型无效",
                cas_number_type=type(cas_number).__name__
            )
            return ServiceResult.fail(
                message="CAS编号必须为字符串类型",
                error_code="INVALID_CAS_NUMBER_TYPE"
            )

        if supplier is not None and not isinstance(supplier, str):
            logger.warning(
                "参数校验失败: 供应商类型无效",
                supplier_type=type(supplier).__name__
            )
            return ServiceResult.fail(
                message="供应商必须为字符串类型",
                error_code="INVALID_SUPPLIER_TYPE"
            )

        if storage_location is not None and not isinstance(storage_location, str):
            logger.warning(
                "参数校验失败: 存储位置类型无效",
                storage_location_type=type(storage_location).__name__
            )
            return ServiceResult.fail(
                message="存储位置必须为字符串类型",
                error_code="INVALID_STORAGE_LOCATION_TYPE"
            )

        if not isinstance(borrowable_only, bool):
            logger.warning(
                "参数校验失败: 可借标记类型无效",
                borrowable_only_type=type(borrowable_only).__name__
            )
            return ServiceResult.fail(
                message="borrowable_only 必须为布尔类型",
                error_code="INVALID_BORROWABLE_ONLY_TYPE"
            )

        # 确定状态过滤
        status = "可借" if borrowable_only else None

        # 数据库层过滤
        results = self.bottle_service.search_multi_condition(
            bottle_number=bottle_number,
            reagent_name=reagent_name,
            cas_number=cas_number,
            supplier=supplier,
            storage_location=storage_location,
            status=status
        )

        logger.info(
            "多条件查询完成",
            bottle_number=bottle_number,
            reagent_name=reagent_name,
            cas_number=cas_number,
            supplier=supplier,
            storage_location=storage_location,
            borrowable_only=borrowable_only,
            result_count=len(results)
        )

        return ServiceResult.ok(
            data=results,
            message=f"查询到 {len(results)} 条匹配记录"
        )

    # ------------------------------------------------------------------
    # 2. 领用历史查询
    # ------------------------------------------------------------------

    @handle_exception(context="查询领用历史")
    def get_borrow_history(
        self,
        bottle_number: Optional[str] = None,
        user: Optional[str] = None
    ) -> ServiceResult[List[Dict[str, Any]]]:
        """查询领用历史记录（数据库层过滤）

        Args:
            bottle_number: 试剂瓶编号（可选，格式如：202606290001）
            user: 领用人姓名（可选，过滤特定用户的记录）

        Returns:
            ServiceResult[List[Dict]]: 领用历史记录列表
        """
        # 参数校验
        if bottle_number is not None:
            if not isinstance(bottle_number, str) or not bottle_number.strip():
                logger.warning(
                    "参数校验失败: 试剂瓶编号无效",
                    bottle_number=bottle_number
                )
                return ServiceResult.fail(
                    message="试剂瓶编号不能为空",
                    error_code="INVALID_BOTTLE_NUMBER"
                )

        if user is not None and not isinstance(user, str):
            logger.warning(
                "参数校验失败: 领用人姓名类型无效",
                user_type=type(user).__name__
            )
            return ServiceResult.fail(
                message="领用人姓名必须为字符串类型",
                error_code="INVALID_USER_TYPE"
            )

        # 数据库层过滤
        records = self.borrow_service.search_multi_condition(
            bottle_number=bottle_number,
            user=user
        )

        # 转换为字典格式
        results = []
        for record in records:
            record_dict = {
                BorrowRecordField.RECORD_NUMBER: getattr(record, BorrowRecordField.RECORD_NUMBER, None),
                BorrowRecordField.BOTTLE_NUMBER: getattr(record, BorrowRecordField.BOTTLE_NUMBER, None),
                BorrowRecordField.REAGENT_NAME: getattr(record, BorrowRecordField.REAGENT_NAME, None),
                BorrowRecordField.USER: getattr(record, BorrowRecordField.USER, None),
                BorrowRecordField.CAS_NUMBER: getattr(record, BorrowRecordField.CAS_NUMBER, None),
                BorrowRecordField.PRODUCTION_DATE: getattr(record, BorrowRecordField.PRODUCTION_DATE, None),
                BorrowRecordField.BORROW_TIME: getattr(record, BorrowRecordField.BORROW_TIME, None),
                BorrowRecordField.APPROVER: getattr(record, BorrowRecordField.APPROVER, None),
                BorrowRecordField.APPROVED: getattr(record, BorrowRecordField.APPROVED, None),
                BorrowRecordField.LINKED_RETURN_RECORD_NUMBER: getattr(record, BorrowRecordField.LINKED_RETURN_RECORD_NUMBER, None),
                BorrowRecordField.LAST_UPDATE_TIME: getattr(record, BorrowRecordField.LAST_UPDATE_TIME, None),
                BorrowRecordField.MODIFIER: getattr(record, BorrowRecordField.MODIFIER, None),
                BorrowRecordField.ID: getattr(record, BorrowRecordField.ID, None),
            }
            results.append(record_dict)

        logger.info(
            "领用历史查询完成",
            bottle_number=bottle_number,
            user=user,
            result_count=len(results)
        )

        return ServiceResult.ok(
            data=results,
            message=f"查询到 {len(results)} 条领用记录"
        )

    # ------------------------------------------------------------------
    # 3. 归还历史查询
    # ------------------------------------------------------------------

    @handle_exception(context="查询归还历史")
    def get_return_history(
        self,
        bottle_number: Optional[str] = None,
        user: Optional[str] = None
    ) -> ServiceResult[List[Dict[str, Any]]]:
        """查询归还历史记录（数据库层过滤）

        Args:
            bottle_number: 试剂瓶编号（可选，格式如：202606290001）
            user: 归还人姓名（可选，过滤特定用户的记录）

        Returns:
            ServiceResult[List[Dict]]: 归还历史记录列表
        """
        # 参数校验
        if bottle_number is not None:
            if not isinstance(bottle_number, str) or not bottle_number.strip():
                logger.warning(
                    "参数校验失败: 试剂瓶编号无效",
                    bottle_number=bottle_number
                )
                return ServiceResult.fail(
                    message="试剂瓶编号不能为空",
                    error_code="INVALID_BOTTLE_NUMBER"
                )

        if user is not None and not isinstance(user, str):
            logger.warning(
                "参数校验失败: 归还人姓名类型无效",
                user_type=type(user).__name__
            )
            return ServiceResult.fail(
                message="归还人姓名必须为字符串类型",
                error_code="INVALID_USER_TYPE"
            )

        # 数据库层过滤
        records = self.return_service.search_multi_condition(
            bottle_number=bottle_number,
            return_user=user
        )

        # 转换为字典格式
        results = []
        for record in records:
            record_dict = {
                ReturnRecordField.RETURN_NUMBER: getattr(record, ReturnRecordField.RETURN_NUMBER, None),
                ReturnRecordField.BOTTLE_NUMBER: getattr(record, ReturnRecordField.BOTTLE_NUMBER, None),
                ReturnRecordField.RETURN_USER: getattr(record, ReturnRecordField.RETURN_USER, None),
                ReturnRecordField.RETURN_TIME: getattr(record, ReturnRecordField.RETURN_TIME, None),
                ReturnRecordField.REMAINING_QUANTITY: getattr(record, ReturnRecordField.REMAINING_QUANTITY, None),
                ReturnRecordField.LINKED_BORROW_RECORD_NUMBER: getattr(record, ReturnRecordField.LINKED_BORROW_RECORD_NUMBER, None),
                ReturnRecordField.LAST_UPDATE_TIME: getattr(record, ReturnRecordField.LAST_UPDATE_TIME, None),
                ReturnRecordField.MODIFIER: getattr(record, ReturnRecordField.MODIFIER, None),
                ReturnRecordField.ID: getattr(record, ReturnRecordField.ID, None),
            }
            results.append(record_dict)

        logger.info(
            "归还历史查询完成",
            bottle_number=bottle_number,
            user=user,
            result_count=len(results)
        )

        return ServiceResult.ok(
            data=results,
            message=f"查询到 {len(results)} 条归还记录"
        )

    # ------------------------------------------------------------------
    # 4. 试剂筛选过滤（供页面调用的统一过滤接口）
    # ------------------------------------------------------------------

    @handle_exception(context="试剂筛选过滤")
    def filter_reagents(
        self,
        keyword: Optional[str] = None,
        reagent_name: Optional[str] = None,
        status: Optional[Union[str, List[str]]] = None,
        borrowable_only: bool = False,
    ) -> ServiceResult[List[ReagentBottle]]:
        """试剂筛选过滤（数据库层过滤，供页面调用的统一过滤接口）

        支持关键词搜索、试剂名称筛选、状态筛选等多种过滤条件的组合使用。
        所有过滤条件之间为 AND 关系（同时满足）。

        Args:
            keyword: 通用关键词（模糊匹配试剂名称、CAS号、试剂瓶编号）
            reagent_name: 试剂名称（模糊匹配）
            status: 状态筛选（字符串或字符串列表，如 "可借" / ["已借出", "耗尽"] / None 表示全部）
            borrowable_only: 是否只显示可借试剂（优先级高于 status 参数）

        Returns:
            ServiceResult[List[ReagentBottle]]: 筛选后的试剂瓶列表
        """
        # 参数校验
        if keyword is not None and not isinstance(keyword, str):
            logger.warning(
                "参数校验失败: keyword 类型无效",
                keyword_type=type(keyword).__name__
            )
            return ServiceResult.fail(
                message="keyword 必须为字符串类型",
                error_code="INVALID_KEYWORD_TYPE"
            )

        if reagent_name is not None and not isinstance(reagent_name, str):
            logger.warning(
                "参数校验失败: 试剂名称类型无效",
                reagent_name_type=type(reagent_name).__name__
            )
            return ServiceResult.fail(
                message="试剂名称必须为字符串类型",
                error_code="INVALID_REAGENT_NAME_TYPE"
            )

        if status is not None and not isinstance(status, (str, list)):
            logger.warning(
                "参数校验失败: 状态筛选值类型无效",
                status_type=type(status).__name__
            )
            return ServiceResult.fail(
                message="status 必须为字符串或字符串列表类型",
                error_code="INVALID_STATUS_TYPE"
            )

        if isinstance(status, list):
            for item in status:
                if not isinstance(item, str):
                    logger.warning(
                        "参数校验失败: 状态列表中包含非字符串元素",
                        item_type=type(item).__name__
                    )
                    return ServiceResult.fail(
                        message="status 列表中的元素必须为字符串类型",
                        error_code="INVALID_STATUS_LIST_ITEM_TYPE"
                    )

        if not isinstance(borrowable_only, bool):
            logger.warning(
                "参数校验失败: borrowable_only 类型无效",
                borrowable_only_type=type(borrowable_only).__name__
            )
            return ServiceResult.fail(
                message="borrowable_only 必须为布尔类型",
                error_code="INVALID_BORROWABLE_ONLY_TYPE"
            )

        # 确定最终的状态筛选
        # borrowable_only 优先级更高
        effective_status = None
        if borrowable_only:
            effective_status = "可借"
        elif status is not None:
            # 如果是列表且只有一个元素，取第一个；否则需要特殊处理
            if isinstance(status, list):
                if len(status) == 1:
                    effective_status = status[0]
                elif len(status) > 1:
                    # 多状态查询需要获取所有匹配的记录后在内存中过滤
                    pass

        # 数据库层查询
        if isinstance(status, list) and len(status) > 1:
            # 多状态：先获取所有匹配的，然后过滤
            # 注意：这种情况下仍需要获取全量数据，但可以先用 keyword 和 reagent_name 过滤
            results = self.bottle_service.search_multi_condition(
                keyword=keyword,
                reagent_name=reagent_name,
                status=None
            )
            # Python 层过滤状态
            effective_status_list = status
            filtered_results = [
                bottle for bottle in results
                if getattr(bottle, ReagentBottleField.BORROWABLE_FLAG, "") in effective_status_list
            ]
        else:
            # 单状态或无状态：直接数据库层过滤
            filtered_results = self.bottle_service.search_multi_condition(
                keyword=keyword,
                reagent_name=reagent_name,
                status=effective_status
            )

        logger.info(
            "试剂筛选过滤完成",
            keyword=keyword,
            reagent_name=reagent_name,
            status=status,
            borrowable_only=borrowable_only,
            effective_status=effective_status,
            result_count=len(filtered_results)
        )

        return ServiceResult.ok(
            data=filtered_results,
            message=f"筛选到 {len(filtered_results)} 条匹配记录"
        )

    # ------------------------------------------------------------------
    # 5. 获取所有试剂
    # ------------------------------------------------------------------

    @handle_exception(context="获取所有试剂")
    def get_all_reagents(self) -> ServiceResult[List[ReagentBottle]]:
        """获取所有试剂瓶列表

        Returns:
            ServiceResult[List[ReagentBottle]]: 所有试剂瓶对象列表
        """
        all_bottles = self.bottle_service.get_all_parsed()

        logger.info(
            "获取所有试剂完成",
            total_count=len(all_bottles)
        )

        return ServiceResult.ok(
            data=all_bottles,
            message=f"共 {len(all_bottles)} 条试剂记录"
        )

    # ------------------------------------------------------------------
    # 6. 管控化学品查询
    # ------------------------------------------------------------------

    @handle_exception(context="获取所有管控化学品")
    def get_all_controlled_chemicals(self) -> ServiceResult[List[ControlledList]]:
        """获取所有管控化学品名录

        Returns:
            ServiceResult[List[ControlledList]]: 管控化学品对象列表
        """
        all_controlled = self.controlled_service.get_all_controlled()

        logger.info(
            "获取所有管控化学品完成",
            total_count=len(all_controlled)
        )

        return ServiceResult.ok(
            data=all_controlled,
            message=f"共 {len(all_controlled)} 条管控化学品记录"
        )


# ============================================================================
# 全局单例实例
# ============================================================================

query_service = QueryService()
