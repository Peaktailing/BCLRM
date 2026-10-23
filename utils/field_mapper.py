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
    # ---- 计量单位（文本类型：g/mL/L/kg 等）----
    UNIT = 'unit'  # 计量单位
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
    # ---- 当前管理人（文本类型，保管权归属，存 person.name）----
    MANAGER = 'manager'  # 当前管理人
    # ---- 可借状态（文本类型：可借/已借出/耗尽/空瓶）----
    # borrowable_flag 是业务状态事实源；borrowable_check 为兼容派生的布尔缓存，
    # 写 flag 时 ReagentBottleService 会自动同步 check。
    BORROWABLE_FLAG = 'borrowable_flag'  # 可借状态（事实源）
    # ---- 可借状态布尔缓存（1=可借, 0=不可借）----
    BORROWABLE_CHECK = 'borrowable_check'  # 可借状态布尔缓存
    # ---- 过期状态（文本类型：正常/即将过期/已过期）----
    EXPIRED_FLAG = 'expired_flag'  # 过期状态
    # ---- 到期日期（YYYY/MM/DD，入库时按未启封有效期计算）----
    EXPIRY_DATE = 'expiry_date'  # 到期日期
    # ---- 报废状态（文本类型：待报废/已报废；空=正常在用）----
    SCRAP_FLAG = 'scrap_flag'  # 报废状态
    # ---- 试剂类型（文本类型，关联试剂类型表）----
    REAGENT_TYPE = 'reagent_type'  # 试剂类型
    # ---- 是否管控（0=否，1=是）----
    IS_CONTROLLED = 'is_controlled'  # 是否管控
    # ---- 存储要求（文本类型，关联存储要求表）----
    STORAGE_REQUIREMENT = 'storage_requirement'  # 存储要求
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID
    # ---- 版本号（每次写入由 BaseService 自增，用于「只能改我看到的那一版」）----
    # 读出来是第几版，写回去就点名第几版；中间有人改过则写入被拒，
    # 而不是用陈旧的值覆盖对方的结论（见 db/base_service.py）。
    REV = 'rev'  # 版本号


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
    # ---- 领用数量（数字类型，归还时用于超量校验）----
    BORROW_QUANTITY = 'borrow_quantity'  # 领用数量
    # ---- 计量单位（文本类型）----
    UNIT = 'unit'  # 计量单位
    # ---- 关联实验课程（整数，关联 experiment_course.id）----
    COURSE_ID = 'course_id'  # 关联实验课程ID
    # ---- 关联实验项目（整数，关联 experiment_item.id）----
    ITEM_ID = 'item_id'  # 关联实验项目ID
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
    # ---- 计量单位（文本类型）----
    UNIT = 'unit'  # 计量单位
    # ---- 本次实际用量（数字类型，= 领用量 - 还入量）----
    USAGE_QUANTITY = 'usage_quantity'  # 本次实际用量
    # ---- 关联借出记录号（文本类型，关联领用记录表）----
    LINKED_BORROW_RECORD_NUMBER = 'linked_borrow_record_number'  # 关联借出记录号
    # ---- 最后更新时间（文本格式）----
    LAST_UPDATE_TIME = 'last_update_time'  # 最后更新时间
    # ---- 修改人（文本类型）----
    MODIFIER = 'modifier'  # 修改人
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class ManagerChangeLogField:
    """管理人变更记录表字段名常量

    记录试剂瓶管理人（保管权归属）的每一次变更，用于追溯保管权历史。
    借出/归还不写入本表；仅显式流转等场景写入。
    """
    ID = 'id'                    # 记录ID
    BOTTLE_NUMBER = 'bottle_number'  # 试剂瓶编号
    REAGENT_NAME = 'reagent_name'    # 试剂名称快照
    OLD_MANAGER = 'old_manager'      # 原管理人
    NEW_MANAGER = 'new_manager'      # 新管理人
    REASON = 'reason'                # 变更原因
    REF_TYPE = 'ref_type'            # 关联单据类型
    REF_ID = 'ref_id'                # 关联单据ID
    REMARK = 'remark'                # 备注
    OPERATOR = 'operator'            # 操作人
    CHANGED_AT = 'changed_at'        # 变更时间


class ReagentDemandField:
    """需求单表字段名常量"""
    ID = 'id'
    DEMAND_NUMBER = 'demand_number'   # 需求单编号
    REQUESTER = 'requester'           # 需求人（领用人）
    ORDER_TYPE = 'order_type'         # 零星领用 / 课程领用
    COURSE_ID = 'course_id'
    ITEM_ID = 'item_id'
    PROJECT_ID = 'project_id'
    COURSE_NAME = 'course_name'       # 课程名快照
    ITEM_NAME = 'item_name'           # 实验名快照
    BORROW_TIME = 'borrow_time'       # 领用时间（用于学期归属）
    STATUS = 'status'                 # 待调配 / 调配中 / 已完成 / 已驳回
    REMARK = 'remark'
    CREATED_BY = 'created_by'
    CREATED_AT = 'created_at'


class ReagentDemandItemField:
    """需求单明细表字段名常量"""
    ID = 'id'
    DEMAND_ID = 'demand_id'
    REAGENT_NAME = 'reagent_name'
    CAS_NUMBER = 'cas_number'
    REQUESTED_QTY = 'requested_qty'   # 需求量


class AllocationOrderField:
    """调配单表字段名常量"""
    ID = 'id'
    ALLOCATION_NUMBER = 'allocation_number'  # 调配单编号
    DEMAND_ID = 'demand_id'
    MANAGER = 'manager'               # 受理管理人
    STATUS = 'status'                 # 待处理 / 已借出 / 已退回
    DEMAND_QTY = 'demand_qty'         # 本单承接需求量
    MANAGER_STOCK_QTY = 'manager_stock_qty'  # 受理人可借存量
    TOTAL_STOCK_QTY = 'total_stock_qty'      # 全院可借存量
    YEAR_DEMAND_QTY = 'year_demand_qty'      # 本年度需求量
    IS_STOCK_SUFFICIENT = 'is_stock_sufficient'  # 存量是否够用(0/1)
    HANDLED_AT = 'handled_at'
    REMARK = 'remark'
    CREATED_BY = 'created_by'
    CREATED_AT = 'created_at'


class AllocationOrderItemField:
    """调配单明细表字段名常量"""
    ID = 'id'
    ALLOCATION_ID = 'allocation_id'
    BOTTLE_NUMBER = 'bottle_number'
    REAGENT_NAME = 'reagent_name'
    QTY = 'qty'
    STATUS = 'status'


class ExperimentCourseField:
    """实验课程表字段名常量

    来源于学院实验分组表，用于领用关联与按课程/人均用量统计。
    """
    ID = 'id'
    SEMESTER = 'semester'            # 学年（如 2026-2027）
    TERM = 'term'                    # 学期（如 1）
    COURSE_NAME = 'course_name'      # 课程名称
    CLASS_NAME = 'class_name'        # 开课班级
    MAJOR = 'major'                  # 开课专业
    TEACHER = 'teacher'              # 任课教师
    STUDENT_COUNT = 'student_count'  # 班级人数
    LOCATION = 'location'            # 上课地点
    COLLEGE = 'college'              # 开课学院


class ExperimentItemField:
    """实验项目表字段名常量"""
    ID = 'id'
    SEMESTER = 'semester'            # 学年
    COURSE_NAME = 'course_name'      # 所属课程名
    SEQ = 'seq'                      # 实验序号
    ITEM_NAME = 'item_name'          # 实验名称


class PurchasePlanField:
    """课程采购单（表头）字段名常量"""
    ID = 'id'
    PLAN_NUMBER = 'plan_number'
    COURSE_NAME = 'course_name'
    SOURCE_SEMESTER = 'source_semester'
    TARGET_SEMESTER = 'target_semester'
    SOURCE_STUDENT_COUNT = 'source_student_count'
    TARGET_STUDENT_COUNT = 'target_student_count'
    STATUS = 'status'
    ITEM_COUNT = 'item_count'
    TOTAL_QUANTITY = 'total_quantity'
    REMARK = 'remark'
    CREATED_BY = 'created_by'
    UPDATED_BY = 'updated_by'


class PurchasePlanItemField:
    """采购单明细字段名常量"""
    ID = 'id'
    PLAN_ID = 'plan_id'
    ITEM_ID = 'item_id'
    ITEM_NAME = 'item_name'
    REAGENT_NAME = 'reagent_name'
    CAS_NUMBER = 'cas_number'
    SOURCE_QUANTITY = 'source_quantity'
    PER_CAPITA_USAGE = 'per_capita_usage'
    STUDENT_COUNT = 'student_count'
    DEMAND_QUANTITY = 'demand_quantity'
    PURCHASE_QUANTITY = 'purchase_quantity'
    CURRENT_STOCK = 'current_stock'
    BOTTLE_NUMBER = 'bottle_number'   # 按采购单入库后回填的试剂瓶编号
    IS_MANUAL = 'is_manual'
    SUPPLIER = 'supplier'
    UNIT_PRICE = 'unit_price'
    REMARK = 'remark'


class BorrowOrderField:
    """领用工单表字段名常量"""
    ID = 'id'
    ORDER_NUMBER = 'order_number'
    ORDER_TYPE = 'order_type'      # 零星领用 / 课程领用
    APPLICANT = 'applicant'        # 领用人
    BORROW_TIME = 'borrow_time'    # 领用时间（学期归属）
    COURSE_ID = 'course_id'
    ITEM_ID = 'item_id'
    COURSE_NAME = 'course_name'
    ITEM_NAME = 'item_name'
    STATUS = 'status'              # 借用中 / 部分归还 / 已归还
    REMARK = 'remark'
    CREATED_BY = 'created_by'
    REQUIREMENT_NUMBER = 'requirement_number'  # 来源需求单号（转单时回填）


class BorrowOrderItemField:
    """领用工单明细字段名常量"""
    ID = 'id'
    ORDER_ID = 'order_id'
    BOTTLE_NUMBER = 'bottle_number'
    REAGENT_NAME = 'reagent_name'
    BORROW_QTY = 'borrow_qty'      # 领用量
    RETURNED_QTY = 'returned_qty'  # 已归还量
    STATUS = 'status'              # 待归还 / 已归还
    REQUIREMENT_LINE_ID = 'requirement_line_id'  # 来源需求行


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
    # ---- 未启封有效时长（天）----
    UNSEALED_SHELF_LIFE = 'unsealed_shelf_life'  # 未启封有效时长（天）
    # ---- 启封有效时长（天）----
    SEALED_SHELF_LIFE = 'sealed_shelf_life'  # 启封有效时长（天）
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
    # ---- 默认未启封有效期（天）----
    DEFAULT_UNSEALED_SHELF_LIFE = 'default_unsealed_shelf_life'  # 默认未启封有效期（天）
    # ---- 默认启封有效期（天）----
    DEFAULT_SEALED_SHELF_LIFE = 'default_sealed_shelf_life'  # 默认启封有效期（天）
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


class RecipeField:
    """配方表字段名常量

    配方的物料侧声明：标题、版本、状态与来源引用。实验属于教学还是科研
    只体现在 source_kind/source_code，不参与任何业务分支。
    """
    # ---- 配方业务键（文本类型，唯一，如 teach:aspirin / research:PRJ-001）----
    RECIPE_KEY = 'recipe_key'  # 配方业务键
    # ---- 标题（文本类型）----
    TITLE = 'title'  # 标题
    # ---- 版本号（整数类型，内容变化即升版）----
    VERSION = 'version'  # 版本号
    # ---- 状态（文本类型：draft / validated / archived）----
    STATUS = 'status'  # 状态
    # ---- 来源类别（文本类型：teaching / research / manual）----
    SOURCE_KIND = 'source_kind'  # 来源类别
    # ---- 来源编码（文本类型，课程/实验名或项目编号）----
    SOURCE_CODE = 'source_code'  # 来源编码
    # ---- 来源标题（文本类型）----
    SOURCE_TITLE = 'source_title'  # 来源标题
    # ---- 负责人（文本类型）----
    OWNER = 'owner'  # 负责人
    # ---- 备注（文本类型）----
    NOTE = 'note'  # 备注
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class RecipeComponentField:
    """配方组分表字段名常量

    一行组分 = 一个物质 + 一个角色 + 一条计量规则。计量规则用
    amount_type 判别，其余列是该规则扁平化后的参数。
    """
    # ---- 所属配方ID（整数类型）----
    RECIPE_ID = 'recipe_id'  # 所属配方ID
    # ---- 显示顺序（整数类型）----
    SEQ = 'seq'  # 显示顺序
    # ---- 角色（文本类型：reactant/reagent/solvent/catalyst/indicator/consumable/product）----
    ROLE = 'role'  # 角色
    # ---- 物质引用键（文本类型，cas:xxx / formula:xxx / name:xxx）----
    SUBSTANCE_KEY = 'substance_key'  # 物质引用键
    # ---- 显示名称（文本类型）----
    DISPLAY_NAME = 'display_name'  # 显示名称
    # ---- CAS号（文本类型）----
    CAS_NUMBER = 'cas_number'  # CAS号
    # ---- 分子式（文本类型）----
    FORMULA = 'formula'  # 分子式
    # ---- 计量方式（文本类型：fixed/per_person/per_batch/equivalents/ratio/concentration）----
    AMOUNT_TYPE = 'amount_type'  # 计量方式
    # ---- 计量数值（数字类型）----
    AMOUNT_VALUE = 'amount_value'  # 计量数值
    # ---- 计量单位（文本类型）----
    AMOUNT_UNIT = 'amount_unit'  # 计量单位
    # ---- 基准组分引用键（文本类型，当量/配比/浓度用）----
    REF_KEY = 'ref_key'  # 基准组分引用键
    # ---- 浓度值（数字类型）----
    CONCENTRATION = 'concentration'  # 浓度值
    # ---- 浓度单位（文本类型，如 mol/L）----
    CONCENTRATION_UNIT = 'concentration_unit'  # 浓度单位
    # ---- 化学计量系数（数字类型）----
    COEFFICIENT = 'coefficient'  # 化学计量系数
    # ---- 纯度要求（数字类型，0~1）----
    PURITY_REQUIRED = 'purity_required'  # 纯度要求
    # ---- 备注（文本类型）----
    NOTE = 'note'  # 备注
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class RequirementSheetField:
    """需求单头表字段名常量

    配方 × 规模 的一次计算结果，只追加不改写：谁在什么库存状态下批的
    这批料，事后查得到。
    """
    # ---- 单据号（文本类型，唯一）----
    SHEET_NUMBER = 'sheet_number'  # 单据号
    # ---- 配方ID（整数类型）----
    RECIPE_ID = 'recipe_id'  # 配方ID
    # ---- 配方业务键（文本类型）----
    RECIPE_KEY = 'recipe_key'  # 配方业务键
    # ---- 单据标题（文本类型）----
    TITLE = 'title'  # 单据标题
    # ---- 状态（文本类型：draft/submitted/approved/issued/closed）----
    STATUS = 'status'  # 状态
    # ---- 人数（整数类型）----
    PERSONS = 'persons'  # 人数
    # ---- 批次数（整数类型）----
    BATCHES = 'batches'  # 批次数
    # ---- 容器体积（数字类型）----
    VESSEL_VOLUME = 'vessel_volume'  # 容器体积
    # ---- 容器体积单位（文本类型）----
    VESSEL_UNIT = 'vessel_unit'  # 容器体积单位
    # ---- 规模说明（文本类型）----
    SCALE_LABEL = 'scale_label'  # 规模说明
    # ---- 申请人（文本类型）----
    REQUESTER = 'requester'  # 申请人
    # ---- 来源类别（文本类型）----
    SOURCE_KIND = 'source_kind'  # 来源类别
    # ---- 来源编码（文本类型）----
    SOURCE_CODE = 'source_code'  # 来源编码
    # ---- 告警摘要（文本类型，JSON 数组）----
    WARNINGS = 'warnings'  # 告警摘要
    # ---- 学年（文本类型，如 2026-2027；9/1 起算）----
    ACADEMIC_YEAR = 'academic_year'  # 学年
    # ---- 对应借出单号（文本类型）：转单后回填 ----
    ORDER_NUMBER = 'order_number'  # 对应借出单号
    # ---- 兑付时间（时间戳）：借出即兑付 ----
    ISSUED_AT = 'issued_at'  # 兑付时间
    # ---- 发料人（文本类型）----
    ISSUED_BY = 'issued_by'  # 发料人
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class RequirementLineField:
    """需求明细表字段名常量

    明细里同时保留「算出来的需求」与「评估时的可用量/缺口」，因此这张
    单子本身就是一份可对账的凭证。
    """
    # ---- 所属需求单ID（整数类型）----
    SHEET_ID = 'sheet_id'  # 所属需求单ID
    # ---- 显示顺序（整数类型）----
    SEQ = 'seq'  # 显示顺序
    # ---- 物质引用键（文本类型）----
    SUBSTANCE_KEY = 'substance_key'  # 物质引用键
    # ---- 显示名称（文本类型）----
    DISPLAY_NAME = 'display_name'  # 显示名称
    # ---- CAS号（文本类型）----
    CAS_NUMBER = 'cas_number'  # CAS号
    # ---- 角色（文本类型）----
    ROLE = 'role'  # 角色
    # ---- 需求数量（数字类型）----
    QUANTITY = 'quantity'  # 需求数量
    # ---- 单位（文本类型）----
    UNIT = 'unit'  # 单位
    # ---- 计量依据（文本类型，如「人均 2 g」）----
    BASIS_TEXT = 'basis_text'  # 计量依据
    # ---- 完整推导（文本类型，如「人均 2 g × 12 人」）----
    EXPLANATION = 'explanation'  # 完整推导
    # ---- 纯度要求（数字类型）----
    PURITY_REQUIRED = 'purity_required'  # 纯度要求
    # ---- 是否受管控（整数类型，0/1）----
    IS_CONTROLLED = 'is_controlled'  # 是否受管控
    # ---- 可用量快照（数字类型）----
    AVAILABLE_QUANTITY = 'available_quantity'  # 可用量快照
    # ---- 缺口快照（数字类型）----
    GAP_QUANTITY = 'gap_quantity'  # 缺口快照
    # ---- 覆盖率快照（数字类型，0~1）----
    COVERAGE_RATIO = 'coverage_ratio'  # 覆盖率快照
    # ---- 累计已兑付量（数字类型，记回本行的 unit）----
    # 兑付粒度是行，不是单头：单头置 issued 会把没发出的行一起吞掉。
    ISSUED_QUANTITY = 'issued_quantity'  # 累计已兑付量
    # ---- 兑付状态（文本类型：open / partial / issued）----
    STATUS = 'status'  # 兑付状态
    # ---- 最后一次兑付本行的借出单号（文本类型）----
    ORDER_NUMBER = 'order_number'  # 兑付借出单号
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID


class CustodianRouteField:
    """保管人路由表字段名常量

    这张表回答「这门课该找谁要料」。它是第一段（受理）能成立的前提：
    没有指派，系统只能去全院撮合，受理人永远看不到自己的缺口。
    """
    # ---- 匹配维度（文本类型：course / project / department / person）----
    SCOPE_TYPE = 'scope_type'  # 匹配维度
    # ---- 匹配键（文本类型，课程名或「课程/班级」、项目号、科室名）----
    SCOPE_KEY = 'scope_key'  # 匹配键
    # ---- 受理管理员（文本类型，person.name）----
    CUSTODIAN = 'custodian'  # 受理管理员
    # ---- 优先级（整数类型，数值小的先匹配）----
    PRIORITY = 'priority'  # 优先级
    # ---- 备注（文本类型）----
    REMARK = 'remark'  # 备注
    # ---- 记录ID（系统自动生成）----
    ID = 'id'  # 记录ID
