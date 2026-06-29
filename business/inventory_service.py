"""化学品入库业务服务

提供化学品入库的核心业务逻辑，包括数据校验、条码生成、编号生成、入库处理等功能。
所有业务规则和数据处理都在本文件中实现，与UI完全解耦。

使用 InventoryService 类封装所有入库相关业务方法，
使用字段常量替代硬编码字段名，使用 logger 和 ServiceResult 统一错误处理。
"""
from services.core.reagent_bottle_service import reagent_bottle_service
from services.base.chemical_service import chemical_service
from services.base.controlled_list_service import controlled_list_service
from services.base.supplier_service import supplier_service
from services.base.storage_location_service import storage_location_service
from services.base.reagent_type_service import reagent_type_service
from models.core.reagent_bottle import ReagentBottle
from utils.id_generator import id_generator
from utils.field_mapper import ReagentBottleField
from utils.error_handler import logger, ServiceResult, ValidationError
from datetime import datetime
from typing import Tuple, List, Optional, Dict, Any


class InventoryService:
    """试剂入库服务类

    封装试剂入库相关的所有业务方法，包括数据校验、管控检查、入库处理、
    批量入库、库存查询、辅助数据查询等功能。

    所有方法返回 ServiceResult 对象，统一成功/失败处理。
    """

    def __init__(self):
        """初始化入库服务

        注入所有依赖的服务实例，便于测试和维护。
        """
        self.reagent_bottle_service = reagent_bottle_service
        self.chemical_service = chemical_service
        self.controlled_list_service = controlled_list_service
        self.supplier_service = supplier_service
        self.storage_location_service = storage_location_service
        self.reagent_type_service = reagent_type_service
        self.id_generator = id_generator
        logger.info("InventoryService 初始化完成")

    # ------------------------------------------------------------------
    # 1. 数据校验
    # ------------------------------------------------------------------

    def validate_inventory_inputs(
        self,
        reagent_name: str,
        cas_number: str,
        remaining_quantity: float,
        specification: float
    ) -> ServiceResult[bool]:
        """校验入库数据有效性

        Args:
            reagent_name: 试剂名称
            cas_number: CAS编号
            remaining_quantity: 剩余量
            specification: 规格

        Returns:
            ServiceResult[bool] - 校验通过返回 True，失败返回 False 及错误信息
        """
        if not reagent_name or not reagent_name.strip():
            logger.warning("入库校验失败: 试剂名称为空")
            return ServiceResult.fail(
                message="试剂名称不能为空",
                error_code="EMPTY_REAGENT_NAME"
            )

        if not cas_number or not cas_number.strip():
            logger.warning("入库校验失败: CAS号为空")
            return ServiceResult.fail(
                message="CAS号不能为空，请先选择试剂名称",
                error_code="EMPTY_CAS_NUMBER"
            )

        if remaining_quantity <= 0:
            logger.warning(
                "入库校验失败: 剩余量非法",
                remaining_quantity=remaining_quantity
            )
            return ServiceResult.fail(
                message="剩余量必须大于0",
                error_code="INVALID_REMAINING_QUANTITY",
                data={"remaining_quantity": remaining_quantity}
            )

        if specification <= 0:
            logger.warning(
                "入库校验失败: 规格非法",
                specification=specification
            )
            return ServiceResult.fail(
                message="规格必须大于0",
                error_code="INVALID_SPECIFICATION",
                data={"specification": specification}
            )

        if remaining_quantity > specification:
            logger.warning(
                "入库校验失败: 剩余量超过规格",
                remaining_quantity=remaining_quantity,
                specification=specification
            )
            return ServiceResult.fail(
                message="剩余量不能超过规格总量",
                error_code="QUANTITY_EXCEEDS_SPECIFICATION",
                data={
                    "remaining_quantity": remaining_quantity,
                    "specification": specification
                }
            )

        try:
            chemicals = self.chemical_service.get_all_parsed()
            chemical_names = {c.name.strip() for c in chemicals if c.name}
            if reagent_name.strip() not in chemical_names:
                logger.warning(
                    "入库校验失败: 试剂名称不在化学品信息表中",
                    reagent_name=reagent_name
                )
                return ServiceResult.fail(
                    message="试剂名称不在化学品信息表中，请先添加",
                    error_code="REAGENT_NOT_FOUND",
                    data={"reagent_name": reagent_name}
                )
        except Exception as e:
            logger.error(
                "校验化学品信息失败",
                exception=e,
                reagent_name=reagent_name
            )
            return ServiceResult.fail(
                message=f"校验化学品信息失败: {str(e)}",
                error_code="CHEMICAL_VALIDATION_ERROR"
            )

        logger.info("入库数据校验通过", reagent_name=reagent_name)
        return ServiceResult.ok(data=True, message="校验通过")

    # ------------------------------------------------------------------
    # 2. 管控检查
    # ------------------------------------------------------------------

    def verify_controlled_status(self, cas: str) -> ServiceResult[Tuple[bool, str]]:
        """检查化学品是否为管控类型

        Args:
            cas: CAS编号

        Returns:
            ServiceResult[Tuple[bool, str]] - (是否管控, 管控类型描述)
        """
        try:
            controlled = self.controlled_list_service.get_by_cas_number(cas)
            if controlled:
                logger.info(
                    "检测到管控化学品",
                    cas=cas,
                    dangerous_type=controlled.dangerous_type
                )
                return ServiceResult.ok(
                    data=(True, controlled.dangerous_type),
                    message=f"管控化学品: {controlled.dangerous_type}"
                )
        except Exception as e:
            logger.error(
                "检查管控状态时发生错误",
                exception=e,
                cas=cas
            )
            return ServiceResult.fail(
                message=f"检查管控状态失败: {str(e)}",
                error_code="CONTROLLED_CHECK_ERROR"
            )

        return ServiceResult.ok(data=(False, ""), message="非管控化学品")

    # ------------------------------------------------------------------
    # 3. 单条入库
    # ------------------------------------------------------------------

    def create_inventory_record(
        self,
        reagent_name: str,
        cas_number: str,
        remaining_quantity: float,
        specification: float,
        purity: Optional[str] = None,
        reagent_type: Optional[str] = None,
        unit_price: Optional[float] = None,
        supplier: Optional[str] = None,
        production_date: Optional[str] = None,
        storage_location: Optional[str] = None
    ) -> ServiceResult[Dict[str, Any]]:
        """创建试剂入库记录

        Args:
            reagent_name: 试剂名称（必填，必须来自化学品信息表）
            cas_number: 试剂CAS编号（自动匹配，只读）
            remaining_quantity: 剩余量（必填，大于0）
            specification: 规格（重量）（必填，大于0）
            purity: 纯度（可选）
            reagent_type: 试剂类型（可选）
            unit_price: 采购单价（可选）
            supplier: 供应商（可选）
            production_date: 生产日期（可选，YYYY-MM-DD格式）
            storage_location: 存储位置（可选）

        Returns:
            ServiceResult[Dict] - 成功时返回包含 bottle_number 和 barcode 的字典
        """
        # 1. 校验输入数据
        validation = self.validate_inventory_inputs(
            reagent_name, cas_number, remaining_quantity, specification
        )
        if validation.is_failure():
            return ServiceResult.fail(
                message=f"{validation.message}",
                error_code=validation.error_code,
                data=validation.data
            )

        # 2. 生成并校验条码唯一性
        barcode = self.id_generator.generate_barcode()
        try:
            existing = self.reagent_bottle_service.get_by_barcode(barcode)
            if existing:
                logger.error(
                    "条码生成冲突",
                    barcode=barcode
                )
                return ServiceResult.fail(
                    message="条码生成冲突，请重试",
                    error_code="BARCODE_CONFLICT"
                )
        except Exception as e:
            logger.error(
                "检查条码唯一性失败",
                exception=e,
                barcode=barcode
            )
            return ServiceResult.fail(
                message=f"检查条码唯一性失败: {str(e)}",
                error_code="BARCODE_CHECK_ERROR"
            )

        # 3. 检查管控状态
        controlled_result = self.verify_controlled_status(cas_number)
        is_controlled = False
        controlled_type = ""
        if controlled_result.is_success():
            is_controlled, controlled_type = controlled_result.data

        # 4. 生成试剂瓶编号
        bottle_no = self.id_generator.generate_bottle_number()
        if not bottle_no or len(bottle_no) < 12:
            logger.error("生成试剂瓶编号失败", bottle_no=bottle_no)
            return ServiceResult.fail(
                message="生成试剂瓶编号失败",
                error_code="BOTTLE_NUMBER_GENERATION_FAILED"
            )

        # 5. 构建入库数据（使用字段常量）
        current_time = datetime.now().strftime("%Y/%m/%d %H:%M")
        is_available = remaining_quantity > 0
        borrowable_text = "可借" if is_available else "耗尽"

        inventory_data = {
            ReagentBottleField.BOTTLE_NUMBER: bottle_no,
            ReagentBottleField.BARCODE: barcode,
            ReagentBottleField.REAGENT_NAME: reagent_name,
            ReagentBottleField.CAS_NUMBER: cas_number,
            ReagentBottleField.REMAINING_QUANTITY: remaining_quantity,
            ReagentBottleField.SPECIFICATION: specification,
            ReagentBottleField.INBOUND_DATE: current_time,
            ReagentBottleField.BORROWABLE_FLAG: borrowable_text,
            ReagentBottleField.BORROWABLE_CHECK: is_available,
            ReagentBottleField.IS_CONTROLLED: 1 if is_controlled else 0
        }

        if purity:
            inventory_data[ReagentBottleField.PURITY] = purity

        if reagent_type:
            inventory_data[ReagentBottleField.REAGENT_TYPE] = reagent_type

        if unit_price and unit_price > 0:
            inventory_data[ReagentBottleField.UNIT_PRICE] = unit_price

        if supplier:
            inventory_data[ReagentBottleField.SUPPLIER] = supplier

        if production_date:
            inventory_data[ReagentBottleField.PRODUCTION_DATE] = production_date

        if storage_location:
            inventory_data[ReagentBottleField.STORAGE_LOCATION] = storage_location

        # 6. 创建入库记录
        try:
            record_id = self.reagent_bottle_service.create(inventory_data)
            if record_id:
                result_msg = f"入库成功！试剂瓶编号：{bottle_no}，条码：{barcode}"
                if is_controlled:
                    result_msg += f"\n注意：该试剂为管控化学品（{controlled_type}）"
                    logger.warning(
                        "入库成功（管控化学品）",
                        bottle_number=bottle_no,
                        barcode=barcode,
                        reagent_name=reagent_name,
                        controlled_type=controlled_type
                    )
                else:
                    logger.info(
                        "入库成功",
                        bottle_number=bottle_no,
                        barcode=barcode,
                        reagent_name=reagent_name
                    )
                return ServiceResult.ok(
                    data={
                        "record_id": record_id,
                        "bottle_number": bottle_no,
                        "barcode": barcode,
                        "is_controlled": is_controlled,
                        "controlled_type": controlled_type
                    },
                    message=result_msg
                )

            logger.error("入库失败: 未返回记录ID", reagent_name=reagent_name)
            return ServiceResult.fail(
                message="入库失败，请检查网络连接",
                error_code="INVENTORY_CREATE_FAILED"
            )
        except Exception as e:
            logger.error(
                "创建入库记录失败",
                exception=e,
                reagent_name=reagent_name,
                bottle_number=bottle_no
            )
            return ServiceResult.fail(
                message=f"创建记录失败: {str(e)}",
                error_code="INVENTORY_CREATE_EXCEPTION"
            )

    # ------------------------------------------------------------------
    # 4. 批量入库
    # ------------------------------------------------------------------

    def process_batch_inventory(
        self,
        items: List[dict]
    ) -> ServiceResult[Dict[str, Any]]:
        """批量处理试剂入库

        Args:
            items: 入库列表，每个元素为dict，包含必要字段

        Returns:
            ServiceResult[Dict] - 包含 success_count, fail_count, failures 的字典
        """
        success_count = 0
        fail_count = 0
        failures = []
        total = len(items)

        logger.info("开始批量入库", total_items=total)

        for index, item in enumerate(items, 1):
            result = self.create_inventory_record(
                reagent_name=item.get("reagent_name", ""),
                cas_number=item.get("cas_number", ""),
                remaining_quantity=item.get("remaining_quantity", 0.0),
                specification=item.get("specification", 0.0),
                purity=item.get("purity"),
                unit_price=item.get("unit_price"),
                supplier=item.get("supplier"),
                production_date=item.get("production_date"),
                storage_location=item.get("storage_location")
            )

            if result.is_success():
                success_count += 1
            else:
                fail_count += 1
                failures.append({
                    "row": index,
                    "reagent_name": item.get("reagent_name", "未知"),
                    "error": result.message
                })

        logger.info(
            "批量入库完成",
            total=total,
            success=success_count,
            failed=fail_count
        )

        return ServiceResult.ok(
            data={
                "success_count": success_count,
                "fail_count": fail_count,
                "failures": failures
            },
            message=f"批量入库完成：成功 {success_count} 条，失败 {fail_count} 条"
        )

    # ------------------------------------------------------------------
    # 5. 库存查询
    # ------------------------------------------------------------------

    def retrieve_inventory_by_barcode(
        self,
        barcode: str
    ) -> ServiceResult[Optional[ReagentBottle]]:
        """根据条码查询入库记录

        Args:
            barcode: 试剂瓶条码

        Returns:
            ServiceResult[Optional[ReagentBottle]] - 找到返回ReagentBottle对象，否则返回None
        """
        try:
            bottle = self.reagent_bottle_service.get_by_barcode(barcode)
            if bottle:
                logger.info(
                    "条码查询成功",
                    barcode=barcode,
                    bottle_number=bottle.bottle_number
                )
            else:
                logger.info("条码查询无结果", barcode=barcode)
            return ServiceResult.ok(data=bottle)
        except Exception as e:
            logger.error(
                "条码查询失败",
                exception=e,
                barcode=barcode
            )
            return ServiceResult.fail(
                message=f"查询条码失败: {str(e)}",
                error_code="BARCODE_QUERY_ERROR"
            )

    def retrieve_all_inventory(self) -> ServiceResult[List[ReagentBottle]]:
        """获取所有试剂瓶库存记录

        Returns:
            ServiceResult[List[ReagentBottle]] - ReagentBottle对象列表
        """
        try:
            bottles = self.reagent_bottle_service.get_all_parsed()
            logger.info("获取全部库存记录", count=len(bottles))
            return ServiceResult.ok(data=bottles)
        except Exception as e:
            logger.error(
                "获取库存列表失败",
                exception=e
            )
            return ServiceResult.fail(
                message=f"获取库存列表失败: {str(e)}",
                error_code="INVENTORY_QUERY_ERROR"
            )

    def filter_inventory(
        self,
        keyword: str
    ) -> ServiceResult[List[ReagentBottle]]:
        """搜索试剂瓶库存

        Args:
            keyword: 搜索关键词（匹配试剂名称、条码、试剂瓶编号）

        Returns:
            ServiceResult[List[ReagentBottle]] - 匹配的ReagentBottle对象列表
        """
        all_result = self.retrieve_all_inventory()
        if all_result.is_failure():
            return all_result

        all_bottles = all_result.data
        if not keyword or not keyword.strip():
            return ServiceResult.ok(data=all_bottles)

        keyword_lower = keyword.lower().strip()
        matched = []

        for bottle in all_bottles:
            name_match = (bottle.reagent_name and
                          keyword_lower in bottle.reagent_name.lower())
            barcode_match = (bottle.barcode and
                             keyword_lower in str(bottle.barcode).lower())
            number_match = (bottle.bottle_number and
                            str(bottle.bottle_number) == keyword_lower)

            if name_match or barcode_match or number_match:
                matched.append(bottle)

        logger.info(
            "库存搜索完成",
            keyword=keyword,
            matched_count=len(matched)
        )
        return ServiceResult.ok(
            data=matched,
            message=f"找到 {len(matched)} 条匹配记录"
        )

    # ------------------------------------------------------------------
    # 6. 辅助数据查询
    # ------------------------------------------------------------------

    def get_available_chemical_names(self) -> ServiceResult[List[str]]:
        """获取可用的化学品名称列表

        Returns:
            ServiceResult[List[str]] - 化学品名称字符串列表
        """
        try:
            chemicals = self.chemical_service.get_all_parsed()
            names = sorted([c.name for c in chemicals if c.name])
            logger.info("获取化学品名称列表", count=len(names))
            return ServiceResult.ok(data=names)
        except Exception as e:
            logger.error(
                "获取化学品名称失败",
                exception=e
            )
            return ServiceResult.fail(
                message=f"获取化学品名称失败: {str(e)}",
                error_code="CHEMICAL_NAME_QUERY_ERROR"
            )

    def get_available_suppliers(self) -> ServiceResult[List[str]]:
        """获取可用的供应商列表

        Returns:
            ServiceResult[List[str]] - 供应商名称字符串列表
        """
        try:
            suppliers = self.supplier_service.get_all()
            names = sorted([s.name for s in suppliers if s.name])
            logger.info("获取供应商列表", count=len(names))
            return ServiceResult.ok(data=names)
        except Exception as e:
            logger.error(
                "获取供应商列表失败",
                exception=e
            )
            return ServiceResult.fail(
                message=f"获取供应商列表失败: {str(e)}",
                error_code="SUPPLIER_QUERY_ERROR"
            )

    def get_available_storage_locations(self) -> ServiceResult[List[str]]:
        """获取可用的存储位置列表

        Returns:
            ServiceResult[List[str]] - 存储位置名称字符串列表
        """
        try:
            locations = self.storage_location_service.get_all()
            names = sorted([l.name for l in locations if l.name])
            logger.info("获取存储位置列表", count=len(names))
            return ServiceResult.ok(data=names)
        except Exception as e:
            logger.error(
                "获取存储位置列表失败",
                exception=e
            )
            return ServiceResult.fail(
                message=f"获取存储位置列表失败: {str(e)}",
                error_code="STORAGE_LOCATION_QUERY_ERROR"
            )

    def get_available_reagent_types(self) -> ServiceResult[List[str]]:
        """获取可用的试剂类型列表

        Returns:
            ServiceResult[List[str]] - 试剂类型名称字符串列表
        """
        try:
            type_names = self.reagent_type_service.get_all_names()
            logger.info("获取试剂类型列表", count=len(type_names))
            return ServiceResult.ok(data=type_names)
        except Exception as e:
            logger.error(
                "获取试剂类型列表失败",
                exception=e
            )
            return ServiceResult.fail(
                message=f"获取试剂类型列表失败: {str(e)}",
                error_code="REAGENT_TYPE_QUERY_ERROR"
            )

    def get_chemical_info_by_name(
        self,
        name: str
    ) -> ServiceResult[Optional[Dict[str, Any]]]:
        """根据名称获取化学品详细信息

        Args:
            name: 化学品名称

        Returns:
            ServiceResult[Optional[Dict]] - 化学品信息字典（包含cas等字段）或None
        """
        try:
            chem = self.chemical_service.get_by_name(name)
            if chem:
                info = {
                    "cas_number": chem.cas_number,
                    "display_name": chem.display_name,
                    "formula": chem.formula,
                    "reagent_type": chem.reagent_type,
                    "storage_requirement": chem.storage_requirement
                }
                logger.info("获取化学品信息成功", name=name)
                return ServiceResult.ok(data=info)
            else:
                logger.info("化学品不存在", name=name)
                return ServiceResult.ok(data=None, message="化学品不存在")
        except Exception as e:
            logger.error(
                "获取化学品信息失败",
                exception=e,
                name=name
            )
            return ServiceResult.fail(
                message=f"获取化学品信息失败: {str(e)}",
                error_code="CHEMICAL_INFO_QUERY_ERROR"
            )


# ============================================================================
# 全局单例实例
# ============================================================================

inventory_service = InventoryService()
