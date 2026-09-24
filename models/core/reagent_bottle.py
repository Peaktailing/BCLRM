"""试剂瓶信息表数据模型

对应 SQLite 表：reagent_bottle（系统主表）

字段说明：
- 试剂瓶编号 -> bottle_number（主键）
- 可借标记 -> borrowable_flag（**事实来源**：可借/已借出/耗尽/空瓶，见 business/bottle_state）
- 可借判断 -> borrowable_check（由 borrowable_flag 同步得出，兼容旧逻辑）
- 报废状态 -> scrap_flag（待报废/已报废；空 = 正常在用）
- 派生状态 -> bottle_status（可借/已借出/耗尽/空瓶/已过期，由业务层计算填充）
"""
from pydantic import BaseModel
from typing import Optional


class ReagentBottle(BaseModel):
    """试剂瓶信息数据模型

    系统主表，存储每个试剂瓶的详细信息，是所有业务操作的核心关联表。
    """
    bottle_number: Optional[str] = None   # 试剂瓶编号（主键）
    barcode: Optional[str] = None           # 条码（用于扫码识别）
    reagent_name: Optional[str] = None      # 试剂名称
    cas_number: Optional[str] = None        # 试剂CAS编号（化学品唯一标识）
    remaining_quantity: Optional[float] = None  # 剩余量（单位：g 或 mL）
    specification: Optional[float] = None   # 规格（原始包装量）
    purity: Optional[str] = None            # 纯度（如：分析纯AR、化学纯CP）
    unit_price: Optional[float] = None      # 采购单价（元）
    supplier: Optional[str] = None          # 供应商
    production_date: Optional[str] = None   # 生产日期
    inbound_date: Optional[str] = None      # 入库日期
    unseal_date: Optional[str] = None       # 启封日期
    last_borrow_time: Optional[str] = None  # 最后借出时间
    last_return_time: Optional[str] = None  # 最后归还时间
    last_return_record_no: Optional[int] = None  # 最后归还记录号
    storage_location: Optional[str] = None  # 存储位置
    borrowable_flag: Optional[str] = None   # 可借标记（事实来源：可借/已借出/耗尽/空瓶）
    reagent_type: Optional[str] = None      # 试剂类型
    is_controlled: Optional[int] = None     # 是否管控（0=否，1=是）
    storage_requirement: Optional[str] = None  # 存储要求
    borrowable_check: Optional[bool] = None    # 可借判断（由 borrowable_flag 同步）
    expired_flag: Optional[str] = None      # 过期状态（正常/即将过期/已过期）
    scrap_flag: Optional[str] = None        # 报废状态（待报废/已报废；空=正常在用）
    bottle_status: Optional[str] = None     # 派生显示状态（可借/已借出/耗尽/空瓶/已过期）
    id: Optional[int] = None                # 自增主键
