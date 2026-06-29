"""权限引擎 - 四层分级权限系统的核心

角色等级（从高到低）:
    4 = 超级管理员 (super_admin) - 系统所有信息更改权限
    3 = 管理员 (admin)           - 管理自己录入的试剂瓶
    2 = 教师 (teacher)          - 可借出试剂
    1 = 学生 (student)          - 仅查看（默认未登录即为学生）

权限检查函数均返回 (bool, message) 元组。
"""

from enum import IntEnum


class Role(IntEnum):
    """角色等级定义 - 数值越大权限越高"""
    STUDENT = 1
    TEACHER = 2
    ADMIN = 3
    SUPER_ADMIN = 4


# 角色显示名称映射
ROLE_LABELS = {
    Role.STUDENT: "学生",
    Role.TEACHER: "教师",
    Role.ADMIN: "管理员",
    Role.SUPER_ADMIN: "超级管理员",
}

ROLE_LABELS_ZH = {
    "student": "学生",
    "teacher": "教师",
    "admin": "管理员",
    "super_admin": "超级管理员",
}

ROLE_KEY_MAP = {
    Role.STUDENT: "student",
    Role.TEACHER: "teacher",
    Role.ADMIN: "admin",
    Role.SUPER_ADMIN: "super_admin",
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


def role_key_from_level(level: int) -> str:
    """从等级数值获取角色 key"""
    for k, v in ROLE_KEY_MAP.items():
        if k.value == level:
            return v.value if hasattr(v, 'value') else v
    return "student"


# ── 权限检查函数 ──────────────────────────────────────────


def can_view_reagents(role_key: str) -> tuple:
    """查看试剂 - 所有角色均可"""
    return True, "允许查看试剂"


def can_add_reagent(role_key: str, current_user: str = None, creator: str = None) -> tuple:
    """新增试剂瓶
    - 超级管理员: 可新增任何试剂
    - 管理员: 可新增（试剂归属自己）
    - 教师/学生: 不可新增
    """
    level = get_role_level(role_key)
    if level >= Role.ADMIN:
        return True, "允许新增试剂"
    return False, "当前角色无新增试剂权限，需要管理员及以上角色"


def can_edit_reagent(role_key: str, current_user: str = None, creator: str = None) -> tuple:
    """编辑试剂瓶
    - 超级管理员: 可编辑所有试剂
    - 管理员: 仅编辑自己创建的试剂
    - 教师/学生: 不可编辑
    """
    level = get_role_level(role_key)
    if level >= Role.SUPER_ADMIN:
        return True, "超级管理员可编辑所有试剂"
    if level >= Role.ADMIN and creator and current_user and creator == current_user:
        return True, f"管理员可编辑自己录入的试剂（创建者: {creator}）"
    if level >= Role.ADMIN:
        return False, "只能编辑自己录入的试剂瓶"
    return False, "当前角色无编辑试剂权限"


def can_delete_reagent(role_key: str, current_user: str = None, creator: str = None) -> tuple:
    """删除试剂瓶
    - 超级管理员: 可删除所有试剂
    - 管理员: 仅删除自己创建的试剂
    - 教师/学生: 不可删除
    """
    level = get_role_level(role_key)
    if level >= Role.SUPER_ADMIN:
        return True, "超级管理员可删除所有试剂"
    if level >= Role.ADMIN and creator and current_user and creator == current_user:
        return True, f"管理员可删除自己录入的试剂（创建者: {creator}）"
    if level >= Role.ADMIN:
        return False, "只能删除自己录入的试剂瓶"
    return False, "当前角色无删除试剂权限"


def can_borrow_reagent(role_key: str) -> tuple:
    """借出试剂
    - 超级管理员/管理员/教师: 可借出
    - 学生: 不可借出
    """
    level = get_role_level(role_key)
    if level >= Role.TEACHER:
        return True, "允许借出试剂"
    return False, "借出试剂需要教师及以上账号"


def can_approve_borrow(role_key: str) -> tuple:
    """审批借出申请
    - 超级管理员: 可审批
    - 教师: 可审批
    - 管理员: 不可审批
    - 学生: 不可审批
    """
    level = get_role_level(role_key)
    if level >= Role.SUPER_ADMIN:
        return True, "超级管理员允许审批借出申请"
    if level == Role.TEACHER:
        return True, "教师允许审批借出申请"
    return False, "审批借出需要教师或超级管理员账号"


def can_manage_users(role_key: str) -> tuple:
    """管理用户账号
    - 超级管理员: 可管理
    - 其他角色: 不可
    """
    level = get_role_level(role_key)
    if level >= Role.SUPER_ADMIN:
        return True, "允许管理用户"
    return False, "用户管理仅限超级管理员"


def can_system_settings(role_key: str) -> tuple:
    """系统设置
    - 超级管理员: 可访问
    - 其他角色: 不可
    """
    level = get_role_level(role_key)
    if level >= Role.SUPER_ADMIN:
        return True, "允许访问系统设置"
    return False, "系统设置仅限超级管理员"


def can_view_all_reagents(role_key: str) -> tuple:
    """查看所有试剂 - 所有角色均可"""
    return True, "允许查看所有试剂"


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
        Role.ADMIN: "✅（自己录入）",
        Role.SUPER_ADMIN: "✅",
    },
    "编辑试剂": {
        Role.STUDENT: "❌",
        Role.TEACHER: "❌",
        Role.ADMIN: "✅（仅自己的）",
        Role.SUPER_ADMIN: "✅（全部）",
    },
    "删除试剂": {
        Role.STUDENT: "❌",
        Role.TEACHER: "❌",
        Role.ADMIN: "✅（仅自己的）",
        Role.SUPER_ADMIN: "✅（全部）",
    },
    "借出试剂": {
        Role.STUDENT: "❌",
        Role.TEACHER: "✅",
        Role.ADMIN: "✅",
        Role.SUPER_ADMIN: "✅",
    },
    "审批借出": {
        Role.STUDENT: "❌",
        Role.TEACHER: "✅",
        Role.ADMIN: "❌",
        Role.SUPER_ADMIN: "✅",
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