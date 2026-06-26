"""试剂瓶信息表数据模型

对应 SQLite 表：reagent_bottle

字段映射说明：
- 试剂瓶编号 -> bottle_number (主键)
- 条码 -> barcode
- 试剂名称 -> reagent_name
- 试剂CAS编号 -> cas_number
- 剩余量 -> remaining_quantity
- 规格（重量） -> specification
- 纯度 -> purity
- 采购单价 -> unit_price
- 供应商 -> supplier
- 生产日期 -> production_date
- 入库日期 -> inbound_date
- 启封日期 -> unseal_date
- 最后借出时间 -> last_borrow_time
- 最后归还时间 -> last_return_time
- 最后归还记录号 -> last_return_record_no
- 存储位置 -> storage_location
- 可借标记 -> borrowable_flag
- 可借标记判断 -> borrowable_check
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class ReagentBottle:
    """试剂瓶信息数据模型
    
    系统主表，存储每个试剂瓶的详细信息，是所有业务操作的核心关联表。
    """
    bottle_number: int            # 试剂瓶编号（主键，数字类型，唯一标识）
    barcode: Optional[str] = None # 条码（文本类型，用于扫码识别）
    reagent_name: Optional[str] = None # 试剂名称（文本类型）
    cas_number: Optional[str] = None   # 试剂CAS编号（文本类型，化学品唯一标识）
    remaining_quantity: Optional[float] = None # 剩余量（数字类型，单位：g或mL）
    specification: Optional[float] = None      # 规格（重量）（数字类型，原始包装量）
    purity: Optional[str] = None   # 纯度（文本类型，如：分析纯AR、化学纯CP）
    unit_price: Optional[float] = None # 采购单价（数字类型，单位：元）
    supplier: Optional[str] = None     # 供应商（文本类型）
    production_date: Optional[str] = None # 生产日期（ISO格式字符串）
    inbound_date: Optional[str] = None    # 入库日期（文本格式：YYYY/MM/DD HH:MM）
    unseal_date: Optional[str] = None     # 启封日期（文本格式：YYYY/MM/DD HH:MM）
    last_borrow_time: Optional[str] = None # 最后借出时间（文本格式：YYYY/MM/DD HH:MM）
    last_return_time: Optional[str] = None # 最后归还时间（文本格式：YYYY/MM/DD HH:MM）
    last_return_record_no: Optional[int] = None # 最后归还记录号（数字类型）
    storage_location: Optional[str] = None     # 存储位置（文本类型，如：危化品存储柜1）
    borrowable_flag: Optional[str] = None      # 可借标记（文本类型：可借/已借出/耗尽）
    borrowable_check: Optional[bool] = None    # 可借标记判断（复选框类型）
    id: Optional[str] = None       # Teable内部记录ID（系统自动生成）