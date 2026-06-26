"""服务模块

该模块包含所有与 SQLite 数据库交互的服务类。

核心业务表服务：
- ReagentBottleService: 试剂瓶信息表服务 (reagent_bottle)
- BorrowRecordService: 领用记录表服务 (borrow_record)
- ReturnRecordService: 归还记录表服务 (return_record)

基础信息表服务：
- ChemicalService: 化学品信息表服务 (chemical_info)
- ControlledListService: 管控化学品名录服务 (controlled_list)
- ReagentTypeService: 试剂类型表服务 (reagent_type)
- StorageRequirementService: 存储要求表服务 (storage_requirement)
- PersonService: 人员信息表服务 (person)
- SupplierService: 试剂供应商表服务 (supplier)
- ManufacturerService: 试剂生产商表服务 (manufacturer)
- StorageLocationService: 存储位置表服务 (storage_location)

每个服务类继承 BaseService，提供 CRUD 操作和特定查询方法。
所有服务都已创建全局实例，可直接导入使用。
"""
# 核心业务表服务
from services.core.reagent_bottle_service import ReagentBottleService, reagent_bottle_service
from services.core.borrow_record_service import BorrowRecordService, borrow_record_service
from services.core.return_record_service import ReturnRecordService, return_record_service

# 基础信息表服务
from services.base.chemical_service import ChemicalService, chemical_service
from services.base.controlled_list_service import ControlledListService, controlled_list_service
from services.base.reagent_type_service import ReagentTypeService, reagent_type_service
from services.base.storage_requirement_service import StorageRequirementService, storage_requirement_service
from services.base.person_service import PersonService, person_service
from services.base.supplier_service import SupplierService, supplier_service
from services.base.manufacturer_service import ManufacturerService, manufacturer_service
from services.base.storage_location_service import StorageLocationService, storage_location_service

__all__ = [
    # 核心业务表服务类
    'ReagentBottleService',
    'BorrowRecordService',
    'ReturnRecordService',
    # 核心业务表服务实例
    'reagent_bottle_service',
    'borrow_record_service',
    'return_record_service',
    # 基础信息表服务类
    'ChemicalService',
    'ControlledListService',
    'ReagentTypeService',
    'StorageRequirementService',
    'PersonService',
    'SupplierService',
    'ManufacturerService',
    'StorageLocationService',
    # 基础信息表服务实例
    'chemical_service',
    'controlled_list_service',
    'reagent_type_service',
    'storage_requirement_service',
    'person_service',
    'supplier_service',
    'manufacturer_service',
    'storage_location_service',
]