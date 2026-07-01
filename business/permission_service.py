"""四层分级权限引擎

角色等级（从高到低）:
    super_admin (4) - 系统数据维护，无借出/审批权限
    admin (3)       - 管理自己录入的试剂瓶，审批自己瓶子的借出
    teacher (2)     - 可借出试剂
    student (1)     - 仅查看（默认未登录即为学生）

权限检查函数均返回 (bool, message) 元组。
"""

# ── 角色定义 ──────────────────────────────────────────────

ROLE_LEVELS = {
    "super_admin": 4,
    "admin": 3,
    "teacher": 2,
    "student": 1,
}

ROLE_LABELS = {
    "super_admin": "超级管理员",
    "admin": "管理员",
    "teacher": "教师",
    "student": "学生",
}


def get_role_level(role: str) -> int:
    return ROLE_LEVELS.get(role, 1)


def get_role_label(role: str) -> str:
    return ROLE_LABELS.get(role, "未知角色")


# ── 权限检查 ──────────────────────────────────────────────

def can_view(role: str) -> tuple:
    """查看试剂 - 所有角色均可"""
    return True, "允许查看试剂"


def can_add_reagent(role: str) -> tuple:
    """新增试剂瓶 - 仅管理员"""
    if get_role_level(role) == ROLE_LEVELS["admin"]:
        return True, "管理员允许新增试剂"
    return False, "新增试剂仅限管理员"


def can_edit_reagent(role: str, current_user_id: str = None, creator_id: str = None) -> tuple:
    """编辑试剂瓶
    - 超级管理员: 可编辑所有试剂（数据维护）
    - 管理员: 仅编辑自己创建的试剂
    """
    level = get_role_level(role)
    if level >= ROLE_LEVELS["super_admin"]:
        return True, "超级管理员可编辑所有试剂（数据维护）"
    if level == ROLE_LEVELS["admin"] and creator_id and current_user_id == creator_id:
        return True, "管理员可编辑自己录入的试剂瓶"
    if level == ROLE_LEVELS["admin"]:
        return False, "只能编辑自己录入的试剂瓶"
    return False, "当前角色无编辑试剂权限"


def can_delete_reagent(role: str, current_user_id: str = None, creator_id: str = None) -> tuple:
    """删除试剂瓶
    - 超级管理员: 可删除所有试剂（数据维护）
    - 管理员: 仅删除自己创建的试剂
    """
    level = get_role_level(role)
    if level >= ROLE_LEVELS["super_admin"]:
        return True, "超级管理员可删除所有试剂（数据维护）"
    if level == ROLE_LEVELS["admin"] and creator_id and current_user_id == creator_id:
        return True, "管理员可删除自己录入的试剂瓶"
    if level == ROLE_LEVELS["admin"]:
        return False, "只能删除自己录入的试剂瓶"
    return False, "当前角色无删除试剂权限"


def can_borrow(role: str) -> tuple:
    """借出试剂
    - 管理员/教师: 可借出
    - 超级管理员: 不可借出（仅系统维护）
    - 学生: 不可借出
    """
    level = get_role_level(role)
    if level in (ROLE_LEVELS["admin"], ROLE_LEVELS["teacher"]):
        return True, "允许借出试剂"
    return False, "借出试剂需要教师或管理员账号"


def can_approve(role: str) -> tuple:
    """审批借出（通用权限检查）- 仅管理员"""
    if get_role_level(role) == ROLE_LEVELS["admin"]:
        return True, "管理员允许审批借出"
    return False, "审批借出仅限管理员"


def can_approve_bottle(role: str, current_user_id: str, bottle_creator_id: str) -> tuple:
    """审批特定试剂瓶的借出 - 仅该瓶所属管理员"""
    if get_role_level(role) != ROLE_LEVELS["admin"]:
        return False, "审批借出仅限管理员"
    if current_user_id == bottle_creator_id:
        return True, "管理员可审批自己试剂瓶的借出"
    return False, "该试剂瓶不属于您，无权审批"


def can_manage_users(role: str) -> tuple:
    """管理用户 - 仅超级管理员"""
    if get_role_level(role) >= ROLE_LEVELS["super_admin"]:
        return True, "允许管理用户"
    return False, "用户管理仅限超级管理员"


def can_system_settings(role: str) -> tuple:
    """系统设置 - 仅超级管理员"""
    if get_role_level(role) >= ROLE_LEVELS["super_admin"]:
        return True, "允许访问系统设置"
    return False, "系统设置仅限超级管理员"


# ── 权限矩阵（用于展示） ──────────────────────────────────

PERMISSION_MATRIX = {
    "查看试剂":   {"student": "✅", "teacher": "✅", "admin": "✅", "super_admin": "✅"},
    "新增试剂":   {"student": "❌", "teacher": "❌", "admin": "✅", "super_admin": "❌"},
    "编辑试剂":   {"student": "❌", "teacher": "❌", "admin": "✅(仅自己的)", "super_admin": "✅(数据维护)"},
    "删除试剂":   {"student": "❌", "teacher": "❌", "admin": "✅(仅自己的)", "super_admin": "✅(数据维护)"},
    "借出试剂":   {"student": "❌", "teacher": "✅", "admin": "✅", "super_admin": "❌"},
    "审批借出":   {"student": "❌", "teacher": "❌", "admin": "✅(仅自己的瓶)", "super_admin": "❌"},
    "用户管理":   {"student": "❌", "teacher": "❌", "admin": "❌", "super_admin": "✅"},
    "系统设置":   {"student": "❌", "teacher": "❌", "admin": "❌", "super_admin": "✅"},
}


# ── 兼容性包装类 ──────────────────────────────────────────

class PermissionService:
    """权限服务类（兼容旧接口）"""

    def check_permission(self, role, action, **kwargs):
        actions = {
            "view": can_view,
            "add_reagent": can_add_reagent,
            "edit_reagent": can_edit_reagent,
            "delete_reagent": can_delete_reagent,
            "borrow": can_borrow,
            "approve": can_approve,
            "manage_users": can_manage_users,
            "system_settings": can_system_settings,
        }
        fn = actions.get(action)
        if not fn:
            return False, f"未知操作: {action}"
        return fn(role, **kwargs) if kwargs else fn(role)

    def can_approve_bottle(self, role, current_user_id, bottle_creator_id):
        return can_approve_bottle(role, current_user_id, bottle_creator_id)

    def get_role_level(self, role):
        return get_role_level(role)

    def get_role_label(self, role):
        return get_role_label(role)

    @staticmethod
    def is_admin(role: str) -> bool:
        return get_role_level(role) >= ROLE_LEVELS["admin"]

    @staticmethod
    def can_borrow_controlled(role: str) -> tuple:
        return can_borrow(role)


permission_service = PermissionService()


# ── 向后兼容的独立函数 ──────────────────────────────────

def check_permission(role: str, action: str, **kwargs) -> tuple:
    """兼容旧接口的权限检查"""
    return permission_service.check_permission(role, action, **kwargs)


def can_borrow_controlled(role: str) -> tuple:
    """兼容旧接口：检查管控试剂领用权限"""
    return can_borrow(role)


def is_admin(role: str) -> bool:
    """兼容旧接口：判断是否为管理员"""
    return get_role_level(role) >= ROLE_LEVELS["admin"]