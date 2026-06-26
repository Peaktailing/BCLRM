"""字段名映射工具

根据开发规范，所有字段名必须在此定义为常量，禁止在代码中直接写字符串。

表结构参考 models/ 目录下的数据模型文件。

常量命名约定：
- 无前缀常量（如 BOTTLE_NUMBER）：英文字段名，用于 Python 模型属性访问和内部逻辑引用
- CN_ 前缀常量（如 CN_BOTTLE_NUMBER）：Teable 表中的中文字段名，用于直接访问 Teable API 返回的 fields 字典

使用示例：
    fields.get(ReagentBottleField.CN_BOTTLE_NUMBER)  # 从 Teable 响应中读取试剂瓶编号
    setattr(bottle, ReagentBottleField.BOTTLE_NUMBER, value)  # 设置 Python 对象属性
"""

# ============================================================================
# 核心业务表字段名常量
# ============================================================================

class ReagentBottleField:
    """试剂瓶信息表字段名常量

    对应 Teable 表：试剂瓶信息表
    系统主表，存储每个试剂瓶的详细信息，是所有业务操作的核心关联表。
    """
    # ---- 试剂瓶编号（主键，数字类型，唯一标识）----
    BOTTLE_NUMBER = 'bottle_number'           # 英文字段名（Python模型属性）
    CN_BOTTLE_NUMBER = '试剂瓶编号'            # Teable中文字段名
    # ---- 条码（文本类型，用于扫码识别）----
    BARCODE = 'barcode'                       # 英文字段名（Python模型属性）
    CN_BARCODE = '条码'                        # Teable中文字段名
    # ---- 试剂名称（文本类型）----
    REAGENT_NAME = 'reagent_name'             # 英文字段名（Python模型属性）
    CN_REAGENT_NAME = '试剂名称'               # Teable中文字段名
    # ---- 试剂CAS编号（文本类型，化学品唯一标识）----
    CAS_NUMBER = 'cas_number'                 # 英文字段名（Python模型属性）
    CN_CAS_NUMBER = '试剂CAS编号'              # Teable中文字段名
    # ---- 剩余量（数字类型，单位：g或mL）----
    REMAINING_QUANTITY = 'remaining_quantity' # 英文字段名（Python模型属性）
    CN_REMAINING_QUANTITY = '剩余量'           # Teable中文字段名
    # ---- 规格（重量）（数字类型，原始包装量）----
    SPECIFICATION = 'specification'           # 英文字段名（Python模型属性）
    CN_SPECIFICATION = '规格（重量）'          # Teable中文字段名
    # ---- 纯度（文本类型，如：分析纯AR、化学纯CP）----
    PURITY = 'purity'                         # 英文字段名（Python模型属性）
    CN_PURITY = '纯度'                         # Teable中文字段名
    # ---- 采购单价（数字类型，单位：元）----
    UNIT_PRICE = 'unit_price'                 # 英文字段名（Python模型属性）
    CN_UNIT_PRICE = '采购单价'                 # Teable中文字段名
    # ---- 供应商（文本类型）----
    SUPPLIER = 'supplier'                     # 英文字段名（Python模型属性）
    CN_SUPPLIER = '供应商'                     # Teable中文字段名
    # ---- 生产日期（ISO格式字符串）----
    PRODUCTION_DATE = 'production_date'       # 英文字段名（Python模型属性）
    CN_PRODUCTION_DATE = '生产日期'            # Teable中文字段名
    # ---- 入库日期（文本格式：YYYY/MM/DD HH:MM）----
    INBOUND_DATE = 'inbound_date'             # 英文字段名（Python模型属性）
    CN_INBOUND_DATE = '入库日期'               # Teable中文字段名
    # ---- 启封日期（文本格式：YYYY/MM/DD HH:MM）----
    UNSEAL_DATE = 'unseal_date'               # 英文字段名（Python模型属性）
    CN_UNSEAL_DATE = '启封日期'                # Teable中文字段名
    # ---- 最后借出时间（文本格式：YYYY/MM/DD HH:MM）----
    LAST_BORROW_TIME = 'last_borrow_time'     # 英文字段名（Python模型属性）
    CN_LAST_BORROW_TIME = '最后借出时间'       # Teable中文字段名
    # ---- 最后归还时间（文本格式：YYYY/MM/DD HH:MM）----
    LAST_RETURN_TIME = 'last_return_time'     # 英文字段名（Python模型属性）
    CN_LAST_RETURN_TIME = '最后归还时间'       # Teable中文字段名
    # ---- 最后归还记录号（数字类型）----
    LAST_RETURN_RECORD_NO = 'last_return_record_no' # 英文字段名（Python模型属性）
    CN_LAST_RETURN_RECORD_NO = '最后归还记录号' # Teable中文字段名
    # ---- 存储位置（文本类型，如：危化品存储柜1）----
    STORAGE_LOCATION = 'storage_location'     # 英文字段名（Python模型属性）
    CN_STORAGE_LOCATION = '存储位置'           # Teable中文字段名
    # ---- 可借标记（文本类型：可借/已借出/耗尽）----
    BORROWABLE_FLAG = 'borrowable_flag'       # 英文字段名（Python模型属性）
    CN_BORROWABLE_FLAG = '可借标记'            # Teable中文字段名
    # ---- 可借标记判断（复选框类型）----
    BORROWABLE_CHECK = 'borrowable_check'     # 英文字段名（Python模型属性）
    CN_BORROWABLE_CHECK = '可借标记判断'       # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


class BorrowRecordField:
    """领用记录表字段名常量

    对应 Teable 表：领用记录表
    记录所有试剂领用操作，用于追踪试剂的使用历史和责任归属。
    """
    # ---- 记录编号（主键，文本类型，格式：L+时间戳）----
    RECORD_NUMBER = 'record_number'           # 英文字段名（Python模型属性）
    CN_RECORD_NUMBER = '记录编号'              # Teable中文字段名
    # ---- 试剂瓶编号（数字类型，关联试剂瓶表）----
    BOTTLE_NUMBER = 'bottle_number'           # 英文字段名（Python模型属性）
    CN_BOTTLE_NUMBER = '试剂瓶编号'            # Teable中文字段名
    # ---- 试剂名称（文本类型）----
    REAGENT_NAME = 'reagent_name'             # 英文字段名（Python模型属性）
    CN_REAGENT_NAME = '试剂名称'               # Teable中文字段名
    # ---- 领用人（文本类型）----
    USER = 'user'                             # 英文字段名（Python模型属性）
    CN_USER = '领用人'                         # Teable中文字段名
    # ---- 试剂CAS编码（文本类型）----
    CAS_NUMBER = 'cas_number'                 # 英文字段名（Python模型属性）
    CN_CAS_NUMBER = '试剂CAS编码'              # Teable中文字段名
    # ---- 生产日期（ISO格式字符串）----
    PRODUCTION_DATE = 'production_date'       # 英文字段名（Python模型属性）
    CN_PRODUCTION_DATE = '生产日期'            # Teable中文字段名
    # ---- 领用时间（文本格式：YYYY/MM/DD HH:MM）----
    BORROW_TIME = 'borrow_time'               # 英文字段名（Python模型属性）
    CN_BORROW_TIME = '领用时间'                # Teable中文字段名
    # ---- 审批人（文本类型，管控试剂必填）----
    APPROVER = 'approver'                     # 英文字段名（Python模型属性）
    CN_APPROVER = '审批人'                     # Teable中文字段名
    # ---- 审批记录上传（文件路径）----
    APPROVAL_FILE = 'approval_file'           # 英文字段名（Python模型属性）
    CN_APPROVAL_FILE = '审批记录上传'          # Teable中文字段名
    # ---- 是否通过审批（复选框类型）----
    APPROVED = 'approved'                     # 英文字段名（Python模型属性）
    CN_APPROVED = '是否通过审批'               # Teable中文字段名
    # ---- 关联归还记录号（文本类型，归还时回填）----
    LINKED_RETURN_RECORD_NUMBER = 'linked_return_record_number' # 英文字段名（Python模型属性）
    CN_LINKED_RETURN_RECORD_NUMBER = '关联归还记录号' # Teable中文字段名
    # ---- 最后更新时间（文本格式）----
    LAST_UPDATE_TIME = 'last_update_time'     # 英文字段名（Python模型属性）
    CN_LAST_UPDATE_TIME = '最后更新时间'       # Teable中文字段名
    # ---- 修改人（文本类型）----
    MODIFIER = 'modifier'                     # 英文字段名（Python模型属性）
    CN_MODIFIER = '修改人'                     # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


class ReturnRecordField:
    """归还记录表字段名常量

    对应 Teable 表：归还记录表
    记录所有试剂归还操作，更新试剂瓶的剩余量状态。
    """
    # ---- 归还记录编号（主键，数字类型，格式：时间戳）----
    RETURN_NUMBER = 'return_number'           # 英文字段名（Python模型属性）
    CN_RETURN_NUMBER = '归还记录 编号'         # Teable中文字段名（注意：中间有空格）
    # ---- 试剂瓶编号（数字类型，关联试剂瓶表）----
    BOTTLE_NUMBER = 'bottle_number'           # 英文字段名（Python模型属性）
    CN_BOTTLE_NUMBER = '试剂瓶编号'            # Teable中文字段名
    # ---- 归还人（文本类型）----
    RETURN_USER = 'return_user'               # 英文字段名（Python模型属性）
    CN_RETURN_USER = '归还人'                  # Teable中文字段名
    # ---- 归还时间（文本格式：YYYY/MM/DD HH:MM）----
    RETURN_TIME = 'return_time'               # 英文字段名（Python模型属性）
    CN_RETURN_TIME = '归还时间'                # Teable中文字段名
    # ---- 归还时余量（数字类型）----
    REMAINING_QUANTITY = 'remaining_quantity' # 英文字段名（Python模型属性）
    CN_REMAINING_QUANTITY = '归还时余量'       # Teable中文字段名
    # ---- 关联借出记录号（文本类型，关联领用记录表）----
    LINKED_BORROW_RECORD_NUMBER = 'linked_borrow_record_number' # 英文字段名（Python模型属性）
    CN_LINKED_BORROW_RECORD_NUMBER = '关联借出记录号' # Teable中文字段名
    # ---- 最后更新时间（文本格式）----
    LAST_UPDATE_TIME = 'last_update_time'     # 英文字段名（Python模型属性）
    CN_LAST_UPDATE_TIME = '最后更新时间'       # Teable中文字段名
    # ---- 修改人（文本类型）----
    MODIFIER = 'modifier'                     # 英文字段名（Python模型属性）
    CN_MODIFIER = '修改人'                     # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


# ============================================================================
# 基础信息表字段名常量
# ============================================================================

class ChemicalInfoField:
    """化学品信息表字段名常量

    对应 Teable 表：化学品信息表
    存储化学品的基础属性信息，包括MSDS、试剂类型、存储要求等。
    """
    # ---- 化学品名称（文本类型，主键标识）----
    NAME = 'name'                             # 英文字段名（Python模型属性）
    CN_NAME = '化学品名称'                     # Teable中文字段名
    # ---- 通用显示名称（文本类型，用于界面展示的常用名称）----
    DISPLAY_NAME = 'display_name'             # 英文字段名（Python模型属性）
    CN_DISPLAY_NAME = '通用显示名称'           # Teable中文字段名
    # ---- 化学式（文本类型）----
    FORMULA = 'formula'                       # 英文字段名（Python模型属性）
    CN_FORMULA = '化学式'                      # Teable中文字段名
    # ---- CAS号（文本类型，化学品唯一标识）----
    CAS = 'cas'                               # 英文字段名（Python模型属性）
    CN_CAS = '化学物质CAS编号'                 # Teable中文字段名
    CN_CAS_ALT = 'CAS号'                       # Teable中文字段名（备用字段名）
    # ---- MSDS附件（文件路径/附件类型）----
    MSDS = 'msds'                             # 英文字段名（Python模型属性）
    CN_MSDS = 'MSDS'                          # Teable中文字段名
    # ---- 试剂类型（关联试剂类型表）----
    REAGENT_TYPE = 'reagent_type'             # 英文字段名（Python模型属性）
    CN_REAGENT_TYPE = '试剂类型'               # Teable中文字段名
    # ---- 存储要求（关联存储要求表）----
    STORAGE_REQUIREMENT = 'storage_requirement' # 英文字段名（Python模型属性）
    CN_STORAGE_REQUIREMENT = '存储要求'        # Teable中文字段名
    # ---- 管控试剂类型（文本类型，如：易制毒、易制爆等）----
    CONTROLLED_TYPE = 'controlled_type'       # 英文字段名（Python模型属性）
    CN_CONTROLLED_TYPE = '管控试剂类型'        # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


class ReagentTypeField:
    """试剂类型表字段名常量

    对应 Teable 表：试剂类型表
    维护试剂的分类信息，如：分析纯、化学纯、色谱纯等。
    """
    # ---- 试剂类型名称（文本类型，主键标识）----
    NAME = 'name'                             # 英文字段名（Python模型属性）
    CN_NAME = '试剂类型'                       # Teable中文字段名
    # ---- 描述（文本类型，备注说明）----
    DESCRIPTION = 'description'               # 英文字段名（Python模型属性）
    CN_DESCRIPTION = '文本'                    # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


class StorageRequirementField:
    """存储要求表字段名常量

    对应 Teable 表：存储要求表
    维护化学品的存储条件信息，如：常温、冷藏、避光等。
    """
    # ---- 存储要求名称（文本类型，主键标识）----
    NAME = 'name'                             # 英文字段名（Python模型属性）
    CN_NAME = '存储要求'                       # Teable中文字段名
    # ---- 描述（文本类型，详细说明）----
    DESCRIPTION = 'description'               # 英文字段名（Python模型属性）
    CN_DESCRIPTION = '文本'                    # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


class PersonField:
    """人员信息表字段名常量

    对应 Teable 表：人员信息表
    维护系统使用人员的基本信息，包括姓名、角色、部门等。
    """
    # ---- 姓名（文本类型，主键标识）----
    NAME = 'name'                             # 英文字段名（Python模型属性）
    CN_NAME = '姓名'                           # Teable中文字段名
    # ---- 角色（文本类型，如：管理员、实验员、审批人）----
    ROLE = 'role'                             # 英文字段名（Python模型属性）
    CN_ROLE = '角色'                           # Teable中文字段名
    # ---- 部门（文本类型）----
    DEPARTMENT = 'department'                 # 英文字段名（Python模型属性）
    CN_DEPARTMENT = '部门'                     # Teable中文字段名
    # ---- 电话（文本类型）----
    PHONE = 'phone'                           # 英文字段名（Python模型属性）
    CN_PHONE = '电话'                          # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


class SupplierField:
    """供应商表字段名常量

    对应 Teable 表：供应商表
    维护试剂供应商的基本信息。
    """
    # ---- 供应商名称（文本类型，主键标识）----
    NAME = 'name'                             # 英文字段名（Python模型属性）
    CN_NAME = '名称'                           # Teable中文字段名
    # ---- 联系人（文本类型）----
    CONTACT = 'contact'                       # 英文字段名（Python模型属性）
    CN_CONTACT = '联系人'                      # Teable中文字段名
    # ---- 电话（文本类型）----
    PHONE = 'phone'                           # 英文字段名（Python模型属性）
    CN_PHONE = '电话'                          # Teable中文字段名
    # ---- 地址（文本类型）----
    ADDRESS = 'address'                       # 英文字段名（Python模型属性）
    CN_ADDRESS = '地址'                        # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


class ManufacturerField:
    """生产商表字段名常量

    对应 Teable 表：试剂生产商表
    维护试剂生产厂商的基本信息。
    """
    # ---- 生产商名称（文本类型，主键标识）----
    NAME = 'name'                             # 英文字段名（Python模型属性）
    CN_NAME = '名称'                           # Teable中文字段名
    # ---- 联系人（文本类型）----
    CONTACT = 'contact'                       # 英文字段名（Python模型属性）
    CN_CONTACT = '联系人'                      # Teable中文字段名
    # ---- 电话（文本类型）----
    PHONE = 'phone'                           # 英文字段名（Python模型属性）
    CN_PHONE = '电话'                          # Teable中文字段名
    # ---- 地址（文本类型）----
    ADDRESS = 'address'                       # 英文字段名（Python模型属性）
    CN_ADDRESS = '地址'                        # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


class StorageLocationField:
    """存储位置表字段名常量

    对应 Teable 表：存储位置表
    维护试剂存储位置信息，如：危化品存储柜、冷藏柜、普通货架等。
    """
    # ---- 存储位置名称（文本类型，主键标识）----
    NAME = 'name'                             # 英文字段名（Python模型属性）
    CN_NAME = '名称'                           # Teable中文字段名
    # ---- 描述（文本类型，位置说明）----
    DESCRIPTION = 'description'               # 英文字段名（Python模型属性）
    CN_DESCRIPTION = '描述'                    # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）


class ControlledListField:
    """管控化学品名录表字段名常量

    对应 Teable 表：管控化学品名录
    维护国家管控的危化品目录，包括易制毒、易制爆等类型的化学品信息。
    """
    # ---- 化学品名称（文本类型）----
    CHEMICAL_NAME = 'chemical_name'           # 英文字段名（Python模型属性）
    CN_CHEMICAL_NAME = '化学品名称'            # Teable中文字段名
    # ---- 化学品别名（文本类型）----
    ALIAS = 'alias'                           # 英文字段名（Python模型属性）
    CN_ALIAS = '化学品别名'                    # Teable中文字段名
    # ---- CAS编号（文本类型，化学品唯一标识）----
    CAS = 'cas'                               # 英文字段名（Python模型属性）
    CN_CAS = 'CAS'                            # Teable中文字段名
    # ---- 危化品类型（文本类型，如：易制毒、易制爆）----
    DANGEROUS_TYPE = 'dangerous_type'         # 英文字段名（Python模型属性）
    CN_DANGEROUS_TYPE = '危化品类型'           # Teable中文字段名
    # ---- Teable内部记录ID（系统自动生成）----
    ID = 'id'                                 # 英文字段名（Python模型属性）
    CN_ID = 'id'                              # Teable内部记录ID（无中文名，与英文一致）
