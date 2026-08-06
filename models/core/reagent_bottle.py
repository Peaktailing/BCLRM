"""试剂瓶信息表数据模型

对应 SQLite 表：reagent_bottle（系统主表）
"""
from pydantic import BaseModel
from typing import Optional


class ReagentBottle(BaseModel):
    """试剂瓶信息数据模型

    系统主表，存储每个试剂瓶的详细信息，是所有业务操作的核心关联表。
    """
    bottle_number: Optional[str] = None
    barcode: Optional[str] = None
    reagent_name: Optional[str] = None
    cas_number: Optional[str] = None
    remaining_quantity: Optional[float] = None
    specification: Optional[float] = None
    purity: Optional[str] = None
    unit_price: Optional[float] = None
    supplier: Optional[str] = None
    production_date: Optional[str] = None
    inbound_date: Optional[str] = None
    unseal_date: Optional[str] = None
    last_borrow_time: Optional[str] = None
    last_return_time: Optional[str] = None
    last_return_record_no: Optional[int] = None
    storage_location: Optional[str] = None
    borrowable_flag: Optional[str] = None  # 废弃，仅用于显示兼容，请使用 borrowable_check
    reagent_type: Optional[str] = None
    is_controlled: Optional[int] = None
    storage_requirement: Optional[str] = None
    borrowable_check: Optional[bool] = None
    expired_flag: Optional[str] = None
    bottle_status: Optional[str] = None  # 派生状态: 可借/已借出/耗尽/已过期，由业务层计算
    id: Optional[int] = None