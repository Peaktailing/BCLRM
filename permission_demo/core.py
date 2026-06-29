"""权限引擎 - 四层分级权限系统的核心

角色等级（从高到低）:
    4 = 超级管理员 (super_admin) - 仅系统数据维护
    3 = 管理员 (admin)           - 管理自己录入的试剂瓶 + 审批自己瓶子的借出
    2 = 教师 (teacher)          - 可借出试剂
    1 = 学生 (student)          - 仅查看（默认未登录即为学生）

权限检查函数均返回 (bool, message) 元组。
"""

from enum import IntEnum


class Role(IntEnum):
    """角色等级定义"""
    STUDENT = 1
    TEACHER = 2
    ADMIN = 3
    SUPER_ADMIN = 4


# 角色显示名称映射
ROLE_LABELS_ZH = {
    "student": "学生",
    "teacher": "教师",
    "admin": "管理员",
    "super_admin": "超级管理员",
}


def get_role_level(role_key: str) -> int:
    """根据角色 key 获取等级数值"""
    mapping = {
        "super_admin": Role.SUPER_ADMIN,
        "admin": Role.ADMIN,
        "teacher": Role.TEACHER,
        "student": Role.STUDENT,
    }
    return mapping.get(role_key, Role.STUDENT)


def get_role_label(role_key: str) -> str:
    """获取角色的中文显示名"""
    return ROLE_LABELS_ZH.get(role_key, "未知角色")


# ── 权限检查函数 ──────────────────────────────────────────


def can_view_reagents(role_key: str) -> tuple:
    """查看试剂 - 所有角色均可"""
    return True, "允许查看试剂"


def can_add_reagent(role_key: str) -> tuple:
    """新增试剂瓶 - 仅管理员"""
    level = get_role_level(role_key)
    if level == Role.ADMIN:
        return True, "管理员允许新增试剂"
    return False, "新增试剂仅限管理员"


def can_edit_reagent(role_key: str, current_user: str = None, creator: str = None) -> tuple:
    """编辑试剂瓶
    - 超级管理员: 可编辑所有试剂（数据维护）
    - 管理员: 仅编辑自己创建的试剂
    - 教师/学生: 不可编辑
    """
    level = get_role_level(role_key)
    if level >= Role.SUPER_ADMIN:
        return True, "超级管理员可编辑所有试剂（数据维护）"
    if level == Role.ADMIN and creator and current_user and creator == current_user:
        return True, f"管理员可编辑自己录入的试剂（创建者: {creator}）"
    if level == Role.ADMIN:
        return False, "只能编辑自己录入的试剂瓶"
    return False, "当前角色无编辑试剂权限"


def can_delete_reagent(role_key: str, current_user: str = None, creator: str = None) -> tuple:
    """删除试剂瓶
    - 超级管理员: 可删除所有试剂（数据维护）
    - 管理员: 仅删除自己创建的试剂
    - 教师/学生: 不可删除
    """
    level = get_role_level(role_key)
    if level >= Role.SUPER_ADMIN:
        return True, "超级管理员可删除所有试剂（数据维护）"
    if level == Role.ADMIN and creator and current_user and creator == current_user:
        return True, f"管理员可删除自己录入的试剂（创建者: {creator}）"
    if level == Role.ADMIN:
        return False, "只能删除自己录入的试剂瓶"
    return False, "当前角色无删除试剂权限"


def can_borrow_reagent(role_key: str) -> tuple:
    """借出试剂
    - 管理员/教师: 可借出
    - 超级管理员: 不可借出（仅系统维护）
    - 学生: 不可借出
    """
    level = get_role_level(role_key)
    if level == Role.ADMIN or level == Role.TEACHER:
        return True, "允许借出试剂"
    return False, "借出试剂需要教师或管理员账号"


def can_approve_borrow(role_key: str) -> tuple:
    """审批借出（通用权限）- 仅管理员有审批入口"""
    level = get_role_level(role_key)
    if level == Role.ADMIN:
        return True, "管理员允许审批借出"
    return False, "审批借出仅限试剂瓶所属管理员"


def can_approve_bottle(role_key: str, current_user: str, bottle_creator: str) -> tuple:
    """审批特定试剂瓶的借出 - 仅该瓶所属管理员"""
    level = get_role_level(role_key)
    if level != Role.ADMIN:
        return False, "审批借出仅限管理员"
    if current_user == bottle_creator:
        return True, f"管理员可审批自己试剂瓶的借出（{bottle_creator}）"
    return False, f"该试剂瓶由 {bottle_creator} 录入，您不是其所有者，无权审批"


def can_manage_users(role_key: str) -> tuple:
    """管理用户账号 - 仅超级管理员"""
    level = get_role_level(role_key)
    if level >= Role.SUPER_ADMIN:
        return True, "允许管理用户"
    return False, "用户管理仅限超级管理员"


def can_system_settings(role_key: str) -> tuple:
    """系统设置 - 仅超级管理员"""
    level = get_role_level(role_key)
    if level >= Role.SUPER_ADMIN:
        return True, "允许访问系统设置"
    return False, "系统设置仅限超级管理员"


# ── 权限汇总表 ────────────────────────────────────────────

PERMISSION_DESCRIPTIONS = {
    "查看试剂": {
        Role.STUDENT: "✅",
        Role.TEACHER: "✅",
        Role.ADMIN: "✅",
        Role.SUPER_ADMIN: "✅",
    },
    "新增试剂": {
        Role.STUDENT: "❌",
        Role.TEACHER: "❌",
        Role.ADMIN: "✅",
        Role.SUPER_ADMIN: "❌",
    },
    "编辑试剂": {
        Role.STUDENT: "❌",
        Role.TEACHER: "❌",
        Role.ADMIN: "✅（仅自己的）",
        Role.SUPER_ADMIN: "✅（数据维护）",
    },
    "删除试剂": {
        Role.STUDENT: "❌",
        Role.TEACHER: "❌",
        Role.ADMIN: "✅（仅自己的）",
        Role.SUPER_ADMIN: "✅（数据维护）",
    },
    "借出试剂": {
        Role.STUDENT: "❌",
        Role.TEACHER: "✅",
        Role.ADMIN: "✅",
        Role.SUPER_ADMIN: "❌",
    },
    "审批借出": {
        Role.STUDENT: "❌",
        Role.TEACHER: "❌",
        Role.ADMIN: "✅（仅自己的瓶）",
        Role.SUPER_ADMIN: "❌",
    },
    "用户管理": {
        Role.STUDENT: "❌",
        Role.TEACHER: "❌",
        Role.ADMIN: "❌",
        Role.SUPER_ADMIN: "✅",
    },
    "系统设置": {
        Role.STUDENT: "❌",
        Role.TEACHER: "❌",
        Role.ADMIN: "❌",
        Role.SUPER_ADMIN: "✅",
    },
}


def get_role_permissions(role_key: str) -> dict:
    """获取某个角色的所有权限摘要"""
    level = get_role_level(role_key)
    result = {}
    for action, perm_map in PERMISSION_DESCRIPTIONS.items():
        for r, val in perm_map.items():
            if r.value == level:
                result[action] = val
                break
    return result