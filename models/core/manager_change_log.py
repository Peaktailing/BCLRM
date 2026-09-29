"""管理人变更记录数据模型

对应 SQLite 表：manager_change_log

记录试剂瓶「管理人（保管权归属）」的每一次变更，用于追溯保管权历史：
- 借出/归还 **不** 写入本表（借还不改变管理人）；
- 仅在「管理权流转」等显式变更管理人的场景写入。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ManagerChangeLog:
    """管理人变更记录"""
    id: Optional[int] = None
    bottle_number: Optional[str] = None    # 试剂瓶编号
    reagent_name: Optional[str] = None     # 试剂名称快照
    old_manager: Optional[str] = None      # 原管理人
    new_manager: Optional[str] = None      # 新管理人
    reason: Optional[str] = None           # 变更原因（如：手工流转）
    ref_type: Optional[str] = None         # 关联单据类型
    ref_id: Optional[str] = None           # 关联单据ID
    remark: Optional[str] = None           # 备注
    operator: Optional[str] = None         # 操作人
    changed_at: Optional[str] = None       # 变更时间（YYYY/MM/DD HH:MM）
