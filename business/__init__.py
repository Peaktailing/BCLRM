"""业务逻辑模块

该模块包含试剂库管理系统的核心业务逻辑。
所有业务能力封装为 Service 类，通过模块级单例实例对外提供。

入库业务 (inventory_service):
- create_inventory_record: 试剂入库
- process_batch_inventory: 批量入库
- retrieve_inventory_by_barcode: 查询入库记录

领用业务 (borrow_service):
- reagent_borrow: 试剂领用
- get_borrow_record: 查询领用记录
- get_borrow_records_by_user: 查询用户领用记录

归还业务 (return_service):
- reagent_return: 试剂归还
- get_return_record: 查询归还记录
- get_return_records_by_user: 查询用户归还记录

查询业务 (query_service):
- search_reagents: 多条件查询试剂
- get_borrow_history: 查询领用历史
- get_return_history: 查询归还历史
- get_all_reagents: 获取所有试剂

统计业务 (dashboard_service):
- get_inventory_stats: 库存统计
- get_borrow_stats: 领用统计
- get_return_stats: 归还统计
- get_supplier_stats: 供应商统计
- get_storage_location_stats: 存储位置统计

化学品管理业务 (chemical_manage_service):
- create_chemical: 创建化学品信息
- update_chemical: 更新化学品信息
- get_all_chemicals: 获取所有化学品
- search_chemicals: 搜索化学品

权限业务 (permission_service):
- check_permission: 检查用户权限
- can_borrow_controlled: 检查管控试剂领用权限
- is_admin: 判断是否为管理员
"""
# 入库业务
from business.inventory_service import inventory_service

# 领用业务
from business.borrow_service import borrow_service

# 归还业务
from business.return_service import return_service

# 查询业务
from business.query_service import query_service

# 统计业务
from business.dashboard_service import dashboard_service

# 化学品管理业务
from business.chemical_service import chemical_manage_service

# 权限业务
from business.permission_service import (
    check_permission,
    can_borrow_controlled,
    is_admin
)

__all__ = [
    # 业务服务实例
    'inventory_service',
    'borrow_service',
    'return_service',
    'query_service',
    'dashboard_service',
    'chemical_manage_service',
    # 权限业务（过程式函数）
    'check_permission',
    'can_borrow_controlled',
    'is_admin',
]
