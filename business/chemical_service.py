"""化学品信息管理业务服务

提供化学品信息的增删改查业务逻辑，包括数据校验、管控试剂匹配等功能。

使用面向对象设计，所有业务方法封装在 ChemicalManageService 类中。
"""
from services.base.chemical_service import chemical_service
from services.base.reagent_type_service import reagent_type_service
from services.base.storage_requirement_service import storage_requirement_service
from services.base.controlled_list_service import controlled_list_service
from models.base.chemical import ChemicalInfo
from utils.field_mapper import ChemicalInfoField, ReagentTypeField
from utils.error_handler import logger, ServiceResult, handle_exception
from typing import Optional, List


class ChemicalManageService:
    """化学品信息管理业务服务类

    封装所有化学品信息管理相关的业务逻辑，包括：
    - 化学品数据校验
    - 管控试剂类型匹配
    - 化学品信息创建
    - 化学品信息更新
    - 化学品信息查询
    - 化学品模糊搜索

    Attributes:
        chemical_service: 化学品基础数据服务实例
        reagent_type_service: 试剂类型服务实例
        storage_requirement_service: 存储要求服务实例
        controlled_list_service: 管控化学品名录服务实例
    """

    def __init__(self):
        """初始化化学品业务服务"""
        self.chemical_service = chemical_service
        self.reagent_type_service = reagent_type_service
        self.storage_requirement_service = storage_requirement_service
        self.controlled_list_service = controlled_list_service

    # ========================================================================
    # 数据校验方法
    # ========================================================================

    @handle_exception(context="化学品数据校验")
    def validate_chemical_data(
        self,
        name: str,
        cas: str,
        reagent_type: str,
        storage_requirement: str
    ) -> ServiceResult:
        """校验化学品数据

        执行完整的化学品数据校验，包括必填项检查、唯一性校验
        以及关联数据有效性验证。

        Args:
            name: 化学品名称
            cas: CAS号
            reagent_type: 试剂类型
            storage_requirement: 存储要求

        Returns:
            ServiceResult: 校验结果，成功时 data 为 None，
                          失败时包含具体错误信息
        """
        # 1. 校验化学品名称
        if not name or not name.strip():
            logger.warning("参数校验失败: 化学品名称不能为空")
            return ServiceResult.fail(
                message="化学品名称不能为空",
                error_code="EMPTY_CHEMICAL_NAME"
            )

        # 2. 校验CAS号
        if not cas or not cas.strip():
            logger.warning("参数校验失败: CAS号不能为空")
            return ServiceResult.fail(
                message="CAS号不能为空",
                error_code="EMPTY_CAS_NUMBER"
            )

        # 3. 校验试剂类型
        if not reagent_type or not reagent_type.strip():
            logger.warning("参数校验失败: 试剂类型不能为空")
            return ServiceResult.fail(
                message="试剂类型不能为空",
                error_code="EMPTY_REAGENT_TYPE"
            )

        # 4. 校验存储要求
        if not storage_requirement or not storage_requirement.strip():
            logger.warning("参数校验失败: 存储要求不能为空")
            return ServiceResult.fail(
                message="存储要求不能为空",
                error_code="EMPTY_STORAGE_REQUIREMENT"
            )

        # 5. 检查化学品名称是否已存在
        existing = self.chemical_service.get_by_name(name.strip())
        if existing:
            logger.warning(
                "化学品名称已存在",
                name=name,
                existing_id=existing.id
            )
            return ServiceResult.fail(
                message=f"化学品名称 '{name}' 已存在",
                error_code="DUPLICATE_CHEMICAL_NAME"
            )

        # 6. 检查CAS号是否已存在
        existing_cas = self.chemical_service.get_by_cas_number(cas.strip())
        if existing_cas:
            logger.warning(
                "CAS号已存在",
                cas=cas,
                existing_id=existing_cas.id
            )
            return ServiceResult.fail(
                message=f"CAS号 '{cas}' 已存在",
                error_code="DUPLICATE_CAS_NUMBER"
            )

        # 7. 检查试剂类型是否存在（支持多个类型，逗号分隔）
        reagent_types = self.reagent_type_service.get_all_types()
        type_names = [t.name for t in reagent_types if t.name]
        selected_types = [t.strip() for t in reagent_type.split(",") if t.strip()]
        for selected_type in selected_types:
            if selected_type not in type_names:
                logger.warning(
                    "试剂类型不存在",
                    reagent_type=selected_type
                )
                return ServiceResult.fail(
                    message=f"试剂类型 '{selected_type}' 不存在",
                    error_code="INVALID_REAGENT_TYPE"
                )

        # 8. 检查存储要求是否存在
        storage_reqs = self.storage_requirement_service.get_all_requirements()
        req_names = [r.name for r in storage_reqs if r.name]
        if storage_requirement not in req_names:
            logger.warning(
                "存储要求不存在",
                storage_requirement=storage_requirement
            )
            return ServiceResult.fail(
                message=f"存储要求 '{storage_requirement}' 不存在",
                error_code="INVALID_STORAGE_REQUIREMENT"
            )

        logger.info("化学品数据校验通过", name=name, cas=cas)
        return ServiceResult.ok(message="校验通过")

    # ========================================================================
    # 管控试剂匹配方法
    # ========================================================================

    @handle_exception(context="管控试剂类型匹配")
    def match_controlled_type(self, cas: str) -> ServiceResult:
        """根据CAS号匹配管控试剂类型

        在管控化学品名录中查找指定CAS号的化学品，
        返回其管控类型（如：剧毒、易制爆、易制毒）。

        Args:
            cas: CAS号

        Returns:
            ServiceResult: 匹配结果，成功时 data 为管控类型字符串，
                          未匹配到时 data 为 None
        """
        # 参数校验
        if not cas or not isinstance(cas, str) or not cas.strip():
            logger.warning("参数校验失败: CAS号不能为空")
            return ServiceResult.fail(
                message="CAS号不能为空",
                error_code="EMPTY_CAS_NUMBER"
            )

        controlled = self.controlled_list_service.get_by_cas_number(cas.strip())
        if controlled:
            dangerous_type = getattr(controlled, 'dangerous_type', None)
            logger.info(
                "匹配到管控试剂",
                cas=cas,
                dangerous_type=dangerous_type
            )
            return ServiceResult.ok(
                data=dangerous_type,
                message=f"匹配到管控试剂类型：{dangerous_type}"
            )

        logger.debug("未匹配到管控试剂", cas=cas)
        return ServiceResult.ok(data=None, message="未匹配到管控试剂")

    # ========================================================================
    # 化学品创建方法
    # ========================================================================

    @handle_exception(context="创建化学品信息")
    def create_chemical(
        self,
        name: str,
        display_name: str,
        formula: str,
        cas: str,
        msds: str,
        reagent_type: str,
        storage_requirement: str,
        unsealed_shelf_life: Optional[int] = None,
        sealed_shelf_life: Optional[int] = None,
    ) -> ServiceResult:
        """创建化学品信息

        执行完整的化学品创建流程，包括数据校验、管控试剂匹配
        和记录创建。

        Args:
            name: 化学品名称（必填）
            display_name: 通用显示名称（可选）
            formula: 化学式（可选）
            cas: CAS号（必填，纯文本）
            msds: MSDS附件（可选）
            reagent_type: 试剂类型（必填，从试剂类型表选择）
            storage_requirement: 存储要求（必填，从存储要求表选择）

        Returns:
            ServiceResult: 创建结果，成功时 data 为创建的记录ID，
                          失败时包含错误信息
        """
        # 1. 数据校验
        validation_result = self.validate_chemical_data(
            name, cas, reagent_type, storage_requirement
        )
        if validation_result.is_failure():
            return ServiceResult.fail(
                message=validation_result.message,
                error_code=validation_result.error_code
            )

        # 2. 自动匹配管控试剂类型
        controlled_type = None
        match_result = self.match_controlled_type(cas)
        if match_result.is_success() and match_result.data:
            controlled_type = match_result.data
            logger.warning(
                "检测到管控化学品",
                name=name,
                cas=cas,
                controlled_type=controlled_type
            )

        # 3. 构建化学品数据字典
        chemical_data = {
            ChemicalInfoField.NAME: name.strip(),
            ChemicalInfoField.DISPLAY_NAME: display_name.strip() if display_name else "",
            ChemicalInfoField.FORMULA: formula.strip() if formula else "",
            ChemicalInfoField.CAS_NUMBER: cas.strip(),
            ChemicalInfoField.MSDS: msds if msds else "",
            ChemicalInfoField.REAGENT_TYPE: reagent_type.strip(),
            ChemicalInfoField.STORAGE_REQUIREMENT: storage_requirement.strip()
        }

        # 如果匹配到管控试剂类型，则添加该字段
        if controlled_type:
            chemical_data[ChemicalInfoField.CONTROLLED_TYPE] = controlled_type

        # 添加有效时长字段（仅当有值时设置）
        if unsealed_shelf_life is not None:
            chemical_data[ChemicalInfoField.UNSEALED_SHELF_LIFE] = unsealed_shelf_life
        if sealed_shelf_life is not None:
            chemical_data[ChemicalInfoField.SEALED_SHELF_LIFE] = sealed_shelf_life

        logger.info(
            "尝试创建化学品记录",
            name=name,
            cas=cas,
            reagent_type=reagent_type
        )

        # 4. 调用服务创建记录
        record_id = self.chemical_service.create(chemical_data)
        if record_id:
            logger.info(
                "化学品创建成功",
                record_id=record_id,
                name=name,
                cas=cas
            )
            message = f"添加成功！化学品名称：{name}"
            if controlled_type:
                message += f"（管控类型：{controlled_type}）"
            return ServiceResult.ok(data=record_id, message=message)
        else:
            logger.error(
                "化学品创建失败",
                name=name,
                cas=cas
            )
            return ServiceResult.fail(
                message="添加失败，请检查网络连接",
                error_code="CREATE_CHEMICAL_FAILED"
            )

    # ========================================================================
    # 化学品更新方法
    # ========================================================================

    @handle_exception(context="更新化学品信息")
    def update_chemical(
        self,
        record_id: str,
        name: str,
        display_name: str,
        formula: str,
        cas: str,
        msds: str,
        reagent_type: str,
        storage_requirement: str,
        unsealed_shelf_life: Optional[int] = None,
        sealed_shelf_life: Optional[int] = None,
    ) -> ServiceResult:
        """更新化学品信息

        执行完整的化学品更新流程，包括记录存在性校验、
        唯一性校验（排除自身）、管控试剂重新匹配和记录更新。

        Args:
            record_id: 记录ID
            name: 化学品名称
            display_name: 通用显示名称
            formula: 化学式
            cas: CAS号
            msds: MSDS附件
            reagent_type: 试剂类型
            storage_requirement: 存储要求

        Returns:
            ServiceResult: 更新结果，成功时 data 为更新的记录ID，
                          失败时包含错误信息
        """
        # 参数校验
        if not record_id or not isinstance(record_id, str) or not record_id.strip():
            logger.warning("参数校验失败: 记录ID不能为空")
            return ServiceResult.fail(
                message="记录ID不能为空",
                error_code="EMPTY_RECORD_ID"
            )

        # 1. 获取原记录
        original = self.chemical_service.get_by_id(record_id)
        if not original:
            logger.warning("记录不存在", record_id=record_id)
            return ServiceResult.fail(
                message="记录不存在",
                error_code="RECORD_NOT_FOUND"
            )

        # 2. 检查化学品名称是否被其他记录使用
        existing = self.chemical_service.get_by_name(name.strip() if name else "")
        if existing and existing.id != record_id:
            logger.warning(
                "化学品名称已被其他记录使用",
                record_id=record_id,
                name=name,
                other_record_id=existing.id
            )
            return ServiceResult.fail(
                message=f"化学品名称 '{name}' 已被其他记录使用",
                error_code="DUPLICATE_CHEMICAL_NAME"
            )

        # 3. 检查CAS号是否被其他记录使用
        existing_cas = self.chemical_service.get_by_cas_number(cas.strip() if cas else "")
        if existing_cas and existing_cas.id != record_id:
            logger.warning(
                "CAS号已被其他记录使用",
                record_id=record_id,
                cas=cas,
                other_record_id=existing_cas.id
            )
            return ServiceResult.fail(
                message=f"CAS号 '{cas}' 已被其他记录使用",
                error_code="DUPLICATE_CAS_NUMBER"
            )

        # 4. 重新匹配管控试剂类型
        controlled_type = None
        if cas and cas.strip():
            match_result = self.match_controlled_type(cas)
            if match_result.is_success() and match_result.data:
                controlled_type = match_result.data
                logger.info(
                    "更新时检测到管控化学品",
                    record_id=record_id,
                    cas=cas,
                    controlled_type=controlled_type
                )

        # 5. 构建更新数据字典
        chemical_data = {
            ChemicalInfoField.NAME: name.strip() if name else "",
            ChemicalInfoField.DISPLAY_NAME: display_name.strip() if display_name else "",
            ChemicalInfoField.FORMULA: formula.strip() if formula else "",
            ChemicalInfoField.CAS_NUMBER: cas.strip() if cas else "",
            ChemicalInfoField.MSDS: msds if msds else "",
            ChemicalInfoField.REAGENT_TYPE: reagent_type.strip() if reagent_type else "",
            ChemicalInfoField.STORAGE_REQUIREMENT: storage_requirement.strip() if storage_requirement else "",
            ChemicalInfoField.CONTROLLED_TYPE: controlled_type,
            ChemicalInfoField.UNSEALED_SHELF_LIFE: unsealed_shelf_life,
            ChemicalInfoField.SEALED_SHELF_LIFE: sealed_shelf_life,
        }

        logger.info(
            "尝试更新化学品记录",
            record_id=record_id,
            name=name
        )

        # 6. 调用服务更新记录
        success = self.chemical_service.update(record_id, chemical_data)
        if success:
            logger.info(
                "化学品更新成功",
                record_id=record_id,
                name=name
            )
            message = f"更新成功！化学品名称：{name}"
            if controlled_type:
                message += f"（管控类型：{controlled_type}）"
            return ServiceResult.ok(data=record_id, message=message)
        else:
            logger.error(
                "化学品更新失败",
                record_id=record_id,
                name=name
            )
            return ServiceResult.fail(
                message="更新失败，请检查网络连接",
                error_code="UPDATE_CHEMICAL_FAILED"
            )

    # ========================================================================
    # 化学品查询方法
    # ========================================================================

    @handle_exception(context="获取所有化学品信息")
    def get_all_chemicals(self) -> ServiceResult:
        """获取所有化学品信息

        返回所有已解析的 ChemicalInfo 对象列表。

        Returns:
            ServiceResult: 查询结果，成功时 data 为 ChemicalInfo 对象列表
        """
        chemicals = self.chemical_service.get_all_parsed()

        logger.info(
            "获取所有化学品信息成功",
            count=len(chemicals)
        )

        return ServiceResult.ok(
            data=chemicals,
            message=f"查询到 {len(chemicals)} 条化学品记录"
        )

    # ========================================================================
    # 辅助数据查询方法
    # ========================================================================

    @handle_exception(context="获取试剂类型名称列表")
    def get_reagent_type_names(self) -> ServiceResult:
        """获取试剂类型名称列表

        Returns:
            ServiceResult: 查询结果，成功时 data 为试剂类型名称列表
        """
        type_names = self.reagent_type_service.get_all_names()

        logger.info(
            "获取试剂类型名称列表成功",
            count=len(type_names)
        )

        return ServiceResult.ok(
            data=type_names,
            message=f"共 {len(type_names)} 种试剂类型"
        )

    @handle_exception(context="获取所有试剂类型详情")
    def get_all_reagent_types(self) -> ServiceResult:
        """获取所有试剂类型详情（含默认有效期）

        Returns:
            ServiceResult: 查询结果，成功时 data 为 ReagentType 对象列表
        """
        types = self.reagent_type_service.get_all_types()
        return ServiceResult.ok(
            data=types,
            message=f"共 {len(types)} 种试剂类型"
        )

    @handle_exception(context="根据试剂类型获取默认有效期")
    def get_default_shelf_life_by_types(self, type_names: list) -> ServiceResult:
        """根据试剂类型名称列表获取默认有效时长（取最短值）

        当选择多个试剂类型时，未启封有效期和启封有效期分别取
        所选类型中最短的值作为默认值。

        Args:
            type_names: 试剂类型名称列表

        Returns:
            ServiceResult: 成功时 data 为 dict，包含 unsealed 和 sealed 两个键
        """
        DEFAULT_UNSEALED = 730
        DEFAULT_SEALED = 365

        if not type_names:
            return ServiceResult.ok(data={
                "unsealed": DEFAULT_UNSEALED,
                "sealed": DEFAULT_SEALED,
            })

        all_types = self.reagent_type_service.get_all_types()

        unsealed_values = []
        sealed_values = []

        for t in all_types:
            if t.name in type_names:
                if t.default_unsealed_shelf_life is not None:
                    unsealed_values.append(t.default_unsealed_shelf_life)
                if t.default_sealed_shelf_life is not None:
                    sealed_values.append(t.default_sealed_shelf_life)

        result_unsealed = min(unsealed_values) if unsealed_values else DEFAULT_UNSEALED
        result_sealed = min(sealed_values) if sealed_values else DEFAULT_SEALED

        logger.info(
            "获取默认有效期成功",
            type_names=type_names,
            unsealed=result_unsealed,
            sealed=result_sealed
        )

        return ServiceResult.ok(data={
            "unsealed": result_unsealed,
            "sealed": result_sealed,
        })

    @handle_exception(context="更新试剂类型默认有效期")
    def update_reagent_type_shelf_life(
        self,
        type_name: str,
        default_unsealed_shelf_life: Optional[int],
        default_sealed_shelf_life: Optional[int],
    ) -> ServiceResult:
        """更新试剂类型的默认有效期

        Args:
            type_name: 试剂类型名称
            default_unsealed_shelf_life: 默认未启封有效期（天）
            default_sealed_shelf_life: 默认启封有效期（天）

        Returns:
            ServiceResult: 更新结果
        """
        reagent_type = self.reagent_type_service.get_by_name(type_name)
        if not reagent_type:
            return ServiceResult.fail(
                message=f"试剂类型 '{type_name}' 不存在",
                error_code="REAGENT_TYPE_NOT_FOUND"
            )

        update_data = {
            ReagentTypeField.DEFAULT_UNSEALED_SHELF_LIFE: default_unsealed_shelf_life,
            ReagentTypeField.DEFAULT_SEALED_SHELF_LIFE: default_sealed_shelf_life,
        }

        success = self.reagent_type_service.update(reagent_type.id, update_data)
        if success:
            return ServiceResult.ok(message=f"试剂类型 '{type_name}' 默认有效期已更新")
        else:
            return ServiceResult.fail(message="更新失败", error_code="UPDATE_FAILED")

    @handle_exception(context="获取存储要求名称列表")
    def get_storage_requirement_names(self) -> ServiceResult:
        """获取存储要求名称列表

        Returns:
            ServiceResult: 查询结果，成功时 data 为存储要求名称列表
        """
        req_names = self.storage_requirement_service.get_all_names()

        logger.info(
            "获取存储要求名称列表成功",
            count=len(req_names)
        )

        return ServiceResult.ok(
            data=req_names,
            message=f"共 {len(req_names)} 种存储要求"
        )

    @handle_exception(context="根据名称获取化学品详情")
    def get_chemical_by_name(self, name: str) -> ServiceResult:
        """根据名称获取化学品详情

        Args:
            name: 化学品名称

        Returns:
            ServiceResult: 查询结果，成功时 data 为 ChemicalInfo 对象，
                          不存在时 data 为 None
        """
        if not name or not isinstance(name, str) or not name.strip():
            logger.warning("参数校验失败: 化学品名称不能为空")
            return ServiceResult.fail(
                message="化学品名称不能为空",
                error_code="EMPTY_CHEMICAL_NAME"
            )

        chemical = self.chemical_service.get_by_name(name.strip())

        if chemical:
            logger.info("获取化学品详情成功", name=name)
            return ServiceResult.ok(data=chemical, message="查询成功")
        else:
            logger.info("化学品不存在", name=name)
            return ServiceResult.ok(data=None, message="化学品不存在")

    # ========================================================================
    # 化学品搜索方法
    # ========================================================================

    @handle_exception(context="搜索化学品")
    def search_chemicals(self, keyword: str) -> ServiceResult:
        """双向模糊搜索化学品

        搜索关键词同时匹配：化学品名称、通用显示名称。
        不区分大小写，只要包含关键词就返回结果。

        Args:
            keyword: 搜索关键词

        Returns:
            ServiceResult: 搜索结果，成功时 data 为匹配的
                          ChemicalInfo 对象列表
        """
        # 获取所有化学品（已解析为ChemicalInfo对象）
        all_chemicals = self.chemical_service.get_all_parsed()

        # 如果关键词为空，返回所有
        if not keyword or not keyword.strip():
            logger.info("搜索关键词为空，返回所有化学品", count=len(all_chemicals))
            return ServiceResult.ok(
                data=all_chemicals,
                message=f"查询到 {len(all_chemicals)} 条化学品记录"
            )

        # 转为小写进行不区分大小写的匹配
        keyword_lower = keyword.lower().strip()

        # 双向模糊匹配：化学品名称、通用显示名称
        matched = []
        for chemical in all_chemicals:
            # 检查化学品名称是否匹配
            name_match = False
            chemical_name = getattr(chemical, ChemicalInfoField.NAME, None)
            if chemical_name:
                name_match = keyword_lower in chemical_name.lower()

            # 检查通用显示名称是否匹配
            display_match = False
            display_name = getattr(chemical, ChemicalInfoField.DISPLAY_NAME, None)
            if display_name:
                display_match = keyword_lower in display_name.lower()

            # 任一字段匹配则返回
            if name_match or display_match:
                matched.append(chemical)

        logger.info(
            "化学品搜索完成",
            keyword=keyword,
            matched_count=len(matched),
            total_count=len(all_chemicals)
        )

        return ServiceResult.ok(
            data=matched,
            message=f"搜索到 {len(matched)} 条匹配记录"
        )


# ============================================================================
# 全局单例实例
# ============================================================================

chemical_manage_service = ChemicalManageService()
