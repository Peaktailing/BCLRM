"""字段名映射工具

根据开发规范，所有字段名必须在此定义为常量，禁止在代码中直接写字符串。

表结构参考 models/ 目录下的数据模型文件。

使用示例：
    setattr(bottle, ReagentBottleField.BOTTLE_NUMBER, value)  # 设置 Python 对象属性
    field = ChemicalInfoField.CAS_NUMBER  # 获取字段名字符串
"""

# ============================================================================
# 核心业务表字段名常量
# ============================================================================

class ReagentBottleField:
    """试剂瓶信息表字段名常量

    系统主表，存储每个试剂瓶的详细信息，是所有业务操作的核心关联表。
    """
    # ---- 试剂瓶编号（主键，TEXT类型，格式：YYYYMMDD+NNNN，如202606290001）----
    BOTTLE_NUMBER = 'bottle_number'  # 试剂瓶编号
    # ---- 条码（文本类型，用于扫码识别）----
    BARCODE = 'barcode'  # 条码
    # ---- 试剂名称（文本类型）----
    REAGENT_NAME = 'reagent_name'  # 试剂名称
    # ---- 试剂CAS编号（文本类型，化学品唯一标识）----
    CAS_NUMBER = 'cas_number'  # 试剂CAS编号
    # ---- 剩余量（数字类型，单位：g或mL）----
    REMAINING_QUANTITY = 'remaining_quantity'  # 剩余量
    # ---- 规格（重量）（数字类型，原始包装量）----
    SPECIFICATION = 'specification'  # 规格（重量）
    # ---- 纯度（文本类型，如：分析纯AR、化学纯CP）----
    PURITY = 'purity'  # 纯度
    # ---- 采购单价（数字类型，单位：元）----
    UNIT_PRICE = 'unit_price'  # 采购单价
    # ---- 供应商（文本类型）----
    SUPPLIER = 'supplier'  # 供应商
    # ---- 生产日期（ISO格式字符串）----
    PRODUCTION_DATE = 'production_date'  # 生产日期
    # ---- 入库日期（文本格式：YYYY/MM/DD HH:MM）----
    INBOUND_DATE = 'inbound_date'  # 入库日期
    # ---- 启封日期（文本格式：YYYY/MM/DD HH:MM）----
    UNSEAL_DATE = 'unseal_date'  # 启封日期
    # ---- 最后借出时间（文本格式：YYYY/MM/DD HH:MM）----
    LAST_BORROW_TIME = 'last_borrow_time'  # 最后借出时间
    # ---- 最后归还时间（文本格式：YYYY/MM/DD HH:MM）----
    LAST_RETURN_TIME = 'last_return_time'  # 最后归还时间
    # ---- 最后归还记录号（数字类型）----
    LAST_RETURN_RECORD_NO = 'last_return_record_no'  # 最后归还记录号
    # ---- 存储位置（文本类型，如：危化品存储柜1）----
    STORAGE_LOCATION = 'storage_location'  # 存储位置
    # ---- 可借标记（文本类型：可借/已借出/耗尽）----
    BORROWABLE_FLAG = 'borrowable_flag'  # 可借标记
    # ---- 可借标记判断（复选框类型）----
    BORROWABLE_CHECK = 'borrowable_check'  # 可借标记判断
    # ---- 过期状态（文本类型：正常/即将过期/已过期）----
    EXPIRED_FLAG = 'expired_flag'  # 过期状态
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class BorrowRecordField:
    """领用记录表字段名常量

    记录所有试剂领用操作，用于追踪试剂的使用历史和责任归属。
    """
    # ---- 记录编号（主键，TEXT类型，格式：YYYYMMDD+NNNN，如202606290001）----
    RECORD_NUMBER = 'record_number'  # 记录编号
    # ---- 试剂瓶编号（数字类型，关联试剂瓶表）----
    BOTTLE_NUMBER = 'bottle_number'  # 试剂瓶编号
    # ---- 试剂名称（文本类型）----
    REAGENT_NAME = 'reagent_name'  # 试剂名称
    # ---- 领用人（文本类型）----
    USER = 'user'  # 领用人
    # ---- 试剂CAS编码（文本类型）----
    CAS_NUMBER = 'cas_number'  # 试剂CAS编码
    # ---- 生产日期（ISO格式字符串）----
    PRODUCTION_DATE = 'production_date'  # 生产日期
    # ---- 领用时间（文本格式：YYYY/MM/DD HH:MM）----
    BORROW_TIME = 'borrow_time'  # 领用时间
    # ---- 审批人（文本类型，管控试剂必填）----
    APPROVER = 'approver'  # 审批人
    # ---- 审批记录上传（文件路径）----
    APPROVAL_FILE = 'approval_file'  # 审批记录上传
    # ---- 是否通过审批（复选框类型）----
    APPROVED = 'approved'  # 是否通过审批
    # ---- 关联归还记录号（文本类型，归还时回填）----
    LINKED_RETURN_RECORD_NUMBER = 'linked_return_record_number'  # 关联归还记录号
    # ---- 最后更新时间（文本格式）----
    LAST_UPDATE_TIME = 'last_update_time'  # 最后更新时间
    # ---- 修改人（文本类型）----
    MODIFIER = 'modifier'  # 修改人
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class ReturnRecordField:
    """归还记录表字段名常量

    记录所有试剂归还操作，更新试剂瓶的剩余量状态。
    """
    # ---- 归还记录编号（主键，TEXT类型，格式：YYYYMMDD+NNNN，如202606290001）----
    RETURN_NUMBER = 'return_number'  # 归还记录编号
    # ---- 试剂瓶编号（数字类型，关联试剂瓶表）----
    BOTTLE_NUMBER = 'bottle_number'  # 试剂瓶编号
    # ---- 归还人（文本类型）----
    RETURN_USER = 'return_user'  # 归还人
    # ---- 归还时间（文本格式：YYYY/MM/DD HH:MM）----
    RETURN_TIME = 'return_time'  # 归还时间
    # ---- 归还时余量（数字类型）----
    REMAINING_QUANTITY = 'remaining_quantity'  # 归还时余量
    # ---- 关联借出记录号（文本类型，关联领用记录表）----
    LINKED_BORROW_RECORD_NUMBER = 'linked_borrow_record_number'  # 关联借出记录号
    # ---- 最后更新时间（文本格式）----
    LAST_UPDATE_TIME = 'last_update_time'  # 最后更新时间
    # ---- 修改人（文本类型）----
    MODIFIER = 'modifier'  # 修改人
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


# ============================================================================
# 基础信息表字段名常量
# ============================================================================

class ChemicalInfoField:
    """化学品信息表字段名常量

    存储化学品的基础属性信息，包括MSDS、试剂类型、存储要求等。
    """
    # ---- 化学品名称（文本类型，主键标识）----
    NAME = 'name'  # 化学品名称
    # ---- 通用显示名称（文本类型，用于界面展示的常用名称）----
    DISPLAY_NAME = 'display_name'  # 通用显示名称
    # ---- 化学式（文本类型）----
    FORMULA = 'formula'  # 化学式
    # ---- CAS号（文本类型，化学品唯一标识）----
    CAS_NUMBER = 'cas_number'  # CAS号
    # ---- MSDS附件（文件路径/附件类型）----
    MSDS = 'msds'  # MSDS附件
    # ---- 试剂类型（关联试剂类型表）----
    REAGENT_TYPE = 'reagent_type'  # 试剂类型
    # ---- 存储要求（关联存储要求表）----
    STORAGE_REQUIREMENT = 'storage_requirement'  # 存储要求
    # ---- 管控试剂类型（文本类型，如：易制毒、易制爆等）----
    CONTROLLED_TYPE = 'controlled_type'  # 管控试剂类型
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class ReagentTypeField:
    """试剂类型表字段名常量

    维护试剂的分类信息，如：分析纯、化学纯、色谱纯等。
    """
    # ---- 试剂类型名称（文本类型，主键标识）----
    NAME = 'name'  # 试剂类型名称
    # ---- 描述（文本类型，备注说明）----
    DESCRIPTION = 'description'  # 描述
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class StorageRequirementField:
    """存储要求表字段名常量

    维护化学品的存储条件信息，如：常温、冷藏、避光等。
    """
    # ---- 存储要求名称（文本类型，主键标识）----
    NAME = 'name'  # 存储要求
    # ---- 描述（文本类型，详细说明）----
    DESCRIPTION = 'description'  # 描述
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class PersonField:
    """人员信息表字段名常量

    维护系统使用人员的基本信息，包括姓名、角色、部门等。
    """
    # ---- 姓名（文本类型，主键标识）----
    NAME = 'name'  # 姓名
    # ---- 角色（文本类型，如：管理员、实验员、审批人）----
    ROLE = 'role'  # 角色
    # ---- 部门（文本类型）----
    DEPARTMENT = 'department'  # 部门
    # ---- 电话（文本类型）----
    PHONE = 'phone'  # 电话
    # ---- 学号/工号（文本类型）----
    STUDENT_OR_WORK_ID = 'student_or_work_id'  # 学号/工号
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class SupplierField:
    """供应商表字段名常量

    维护试剂供应商的基本信息。
    """
    # ---- 供应商名称（文本类型，主键标识）----
    NAME = 'name'  # 供应商名称
    # ---- 联系人（文本类型）----
    CONTACT = 'contact'  # 联系人
    # ---- 电话（文本类型）----
    PHONE = 'phone'  # 电话
    # ---- 地址（文本类型）----
    ADDRESS = 'address'  # 地址
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class ManufacturerField:
    """生产商表字段名常量

    维护试剂生产厂商的基本信息。
    """
    FULL_NAME = 'full_name'               # 生产商全称
    BRAND_NAME = 'brand_name'             # 品牌名称
    WEBSITE = 'website'                   # 官方网址
    ATTACHMENT = 'attachment'             # 附件
    ID = 'id'                             # 自增主键


class StorageLocationField:
    """存储位置表字段名常量

    维护试剂存储位置信息，如：危化品存储柜、冷藏柜、普通货架等。
    """
    # ---- 存储位置名称（文本类型，主键标识）----
    NAME = 'name'  # 存储位置名称
    # ---- 描述（文本类型，位置说明）----
    DESCRIPTION = 'description'  # 描述
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class ControlledListField:
    """管控化学品名录表字段名常量

    维护国家管控的危化品目录，包括易制毒、易制爆等类型的化学品信息。
    """
    # ---- 化学品名称（文本类型）----
    CHEMICAL_NAME = 'chemical_name'  # 化学品名称
    # ---- 化学品别名（文本类型）----
    ALIAS = 'alias'  # 化学品别名
    # ---- CAS号（文本类型，化学品唯一标识）----
    CAS_NUMBER = 'cas_number'  # CAS号
    # ---- 危化品类型（文本类型，如：易制毒、易制爆）----
    DANGEROUS_TYPE = 'dangerous_type'  # 危化品类型
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID
