from dataclasses import dataclass
from typing import Optional

# 化学品信息表（tblekF6RbxeM8hxKg5Z）
@dataclass
class ChemicalInfo:
    name: str                     # 化学品名称（主键）
    display_name: Optional[str] = None   # 通用显示名称
    formula: Optional[str] = None        # 化学式
    cas_number: Optional[str] = None     # 化学物质CAS编号
    msds: Optional[str] = None           # MSDS
    reagent_type: Optional[str] = None   # 试剂类型
    storage_req: Optional[str] = None    # 存储要求
    controlled_type: Optional[str] = None # 管控试剂类型
    id: Optional[str] = None             # Teable 内部记录 ID

# 试剂瓶信息表（tblc71S7dbkg0VuBPhO）
@dataclass
class ReagentBottle:
    bottle_number: int            # 试剂瓶编号（主键，数字）
    barcode: str                  # 条码
    reagent_name: str             # 试剂名称（文本）
    cas_number: str               # 试剂CAS编号
    remaining_quantity: float     # 剩余量（数字）
    specification: float          # 规格（重量）（数字）
    purity: Optional[str] = None  # 纯度
    reagent_type: Optional[str] = None   # 试剂类型
    is_controlled: Optional[str] = None  # 是否管控（文本）
    storage_req: Optional[str] = None    # 存储要求
    unit_price: Optional[float] = None   # 采购单价
    supplier: Optional[str] = None       # 供应商（文本）
    production_date: Optional[str] = None # 生产日期（ISO）
    inbound_date: Optional[str] = None    # 入库日期
    unseal_date: Optional[str] = None     # 启封日期
    last_borrow_time: Optional[str] = None
    last_return_time: Optional[str] = None
    last_return_record_no: Optional[int] = None
    storage_location: Optional[str] = None # 存储位置（文本）
    borrowable_flag: Optional[str] = "可借"  # 可借标记（文本，决定状态）
    borrowable_check: Optional[bool] = False # 可借标记判断（复选框）
    id: Optional[str] = None       # Teable 内部记录 ID

# 领用记录表（tbltQ6rcCFngZUABHrO）
@dataclass
class BorrowRecord:
    record_number: str            # 记录编号（主键，文本）
    bottle_number: int            # 试剂瓶编号（数字，关联试剂瓶）
    reagent_name: str             # 试剂名称
    user: str                     # 领用人
    cas_number: str               # 试剂CAS编码
    production_date: Optional[str] = None # 生产日期
    is_controlled: Optional[str] = None   # 是否管控试剂
    borrow_time: Optional[str] = None     # 领用时间
    approver: Optional[str] = None        # 审批人
    approval_file: Optional[str] = None   # 审批记录上传
    approved: Optional[bool] = False      # 是否通过审批
    illegal: Optional[bool] = False       # 是否违规借出管控试剂
    id: Optional[str] = None

# 归还记录表（tblJhsv7PMN64TDrI1P）
@dataclass
class ReturnRecord:
    return_number: int            # 归还记录编号（主键，数字）
    bottle_number: int            # 试剂瓶编号
    return_user: str              # 归还人
    return_time: Optional[str] = None   # 归还时间
    remaining_quantity: float     # 归还时余量
    last_update_time: Optional[str] = None
    modifier: Optional[str] = None
    id: Optional[str] = None

# 管控化学品名录（tblADJrUzMY7y8e0JyO）
@dataclass
class ControlledList:
    chemical_name: str            # 化学品名称（主键）
    alias: Optional[str] = None   # 化学品别名
    cas: Optional[str] = None     # CAS
    dangerous_type: Optional[str] = None # 危化品类型
    id: Optional[str] = None