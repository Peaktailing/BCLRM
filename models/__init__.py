"""数据模型模块

该模块包含所有与Teable数据库表对应的数据模型类。

核心业务表模型：
- ReagentBottle: 试剂瓶信息表（系统主表）
- BorrowRecord: 领用记录表
- ReturnRecord: 归还记录表

基础信息表模型：
- ChemicalInfo: 化学品信息表
- ControlledList: 管控化学品名录表
- ReagentType: 试剂类型表
- StorageRequirement: 存储要求表
- Person: 人员信息表
- Supplier: 试剂供应商表
- Manufacturer: 试剂生产商表
- StorageLocation: 存储位置表

所有模型均使用dataclass定义，字段名与Teable表字段一一对应。
"""
from models.core.reagent_bottle import ReagentBottle
from models.core.borrow_record import BorrowRecord
from models.core.return_record import ReturnRecord
from models.base.chemical import ChemicalInfo
from models.base.controlled_list import ControlledList
from models.base.reagent_type import ReagentType
from models.base.storage_requirement import StorageRequirement
from models.base.person import Person
from models.base.supplier import Supplier
from models.base.manufacturer import Manufacturer
from models.base.storage_location import StorageLocation

__all__ = [
    # 核心业务表模型
    'ReagentBottle',
    'BorrowRecord',
    'ReturnRecord',
    # 基础信息表模型
    'ChemicalInfo',
    'ControlledList',
    'ReagentType',
    'StorageRequirement',
    'Person',
    'Supplier',
    'Manufacturer',
    'StorageLocation',
]