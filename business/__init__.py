"""业务逻辑模块

该模块包含试剂库管理系统的核心业务逻辑。

入库业务：
- reagent_inventory: 试剂入库
- batch_inventory: 批量入库
- get_inventory_by_bottle_number: 查询入库记录

领用业务：
- reagent_borrow: 试剂领用
- get_borrow_record: 查询领用记录
- get_borrow_records_by_user: 查询用户领用记录

归还业务：
- reagent_return: 试剂归还
- batch_return: 批量归还
- get_return_record: 查询归还记录
- get_return_records_by_user: 查询用户归还记录

查询业务：
- search_reagents: 多条件查询试剂
- get_borrow_history: 查询领用历史
- get_return_history: 查询归还历史
- get_all_reagents: 获取所有试剂

统计业务：
- get_inventory_stats: 库存统计
- get_borrow_stats: 领用统计
- get_return_stats: 归还统计
- get_supplier_stats: 供应商统计
- get_storage_location_stats: 存储位置统计
- get_pending_approval_count: 待审批数量

权限业务：
- check_permission: 检查用户权限
- can_borrow_controlled: 检查管控试剂领用权限
- is_admin: 判断是否为管理员
"""
# 入库业务
from business.inventory_service import (
    reagent_inventory,
    batch_inventory,
    get_inventory_by_bottle_number
)

# 领用业务
from business.borrow_service import (
    reagent_borrow,
    get_borrow_record,
    get_borrow_records_by_user
)

# 归还业务
from business.return_service import (
    reagent_return,
    batch_return,
    get_return_record,
    get_return_records_by_user
)

# 查询业务
from business.query_service import (
    search_reagents,
    get_borrow_history,
    get_return_history,
    get_all_reagents
)

# 统计业务
from business.dashboard_service import (
    get_inventory_stats,
    get_borrow_stats,
    get_return_stats,
    get_supplier_stats,
    get_storage_location_stats,
    get_pending_approval_count
)

# 权限业务
from business.permission_service import (
    check_permission,
    can_borrow_controlled,
    is_admin
)

__all__ = [
    # 入库业务
    'reagent_inventory',
    'batch_inventory',
    'get_inventory_by_bottle_number',
    # 领用业务
    'reagent_borrow',
    'get_borrow_record',
    'get_borrow_records_by_user',
    # 归还业务
    'reagent_return',
    'batch_return',
    'get_return_record',
    'get_return_records_by_user',
    # 查询业务
    'search_reagents',
    'get_borrow_history',
    'get_return_history',
    'get_all_reagents',
    # 统计业务
    'get_inventory_stats',
    'get_borrow_stats',
    'get_return_stats',
    'get_supplier_stats',
    'get_storage_location_stats',
    'get_pending_approval_count',
    # 权限业务
    'check_permission',
    'can_borrow_controlled',
    'is_admin',
]