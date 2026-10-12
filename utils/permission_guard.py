"""集中式服务端写权限守卫

统一入口：db/base_service.py 在执行任何写操作前调用 enforce_write()。

设计原则（与页面级权限互补）：
- 页面级：控制按钮可见性，防误操作（components/auth.py）
- 服务端守卫：数据库写入前的最后拦截，防页面漏判/直接调用绕过
- 规则全部集中在本文件，新增敏感表/敏感字段只需在此追加一行，
  无需改动任何业务代码（这就是「不逐笔加校验」的统一方案）

放行策略：
- 无上下文（None）→ 放行：命令行脚本、单元测试、启动初始化等可信场景
- 有上下文 → 按规则校验，不满足则抛 PermissionDeniedError
"""
from typing import Dict, Optional

from utils.error_handler import PermissionDeniedError
from utils.user_context import get_user_name, get_user_role

# 角色层级：super_admin > admin > teacher > user
ADMIN_ROLES = {"admin", "super_admin"}

# 规则1：整表写保护 —— 这些表的任何写操作都要求管理员及以上
#   person          用户与密码/角色管理（password_hash 自助豁免见 SELF_SERVICE_FIELDS）
#   controlled_list 管控化学品名录（页面只读，仅数据维护时开放）
ADMIN_WRITE_TABLES = {
    "person",
    "controlled_list",
}

# 自助豁免字段：仅写入这些字段时无需管理员（用户修改自己的密码）
# 注意：行级约束见 _is_self_service——只能改自己的密码，
#       防止未来新增写 password_hash 的路径成为横向越权通道（QA 审查发现）
SELF_SERVICE_FIELDS = {
    "password_hash",
}

# 标识「目标行归属本人」的字段名（person 表用户名为 name）
_IDENTITY_FIELDS = {"name", "username"}

# 规则2：字段级写保护（**更新场景**；创建时的初始指派放行）
#   manager 管理权变更（transfer/bulk_assign 等流转操作）
#   普通用户的领用/归还/入库创建不写该字段，不会被误伤
ADMIN_WRITE_FIELDS = {
    "manager",
}

# 规则3：审批「决定值」保护（任何场景，按写入值判断）
#   仅写入审批决定（已批准/已驳回）需要管理员；
#   创建工单的初值（待审批/无需审批）与提交审批（待审批）放行，
#   避免误伤教师课程领用等正常发起流程
#   值需与 models/core/borrow_order.py 的 APPROVAL_* 常量保持同步
ADMIN_DECISION_FIELDS = {
    "approval_status",
}
ADMIN_DECISION_VALUES = {
    "已批准",
    "已驳回",
}


def _is_self_service(row_identity: Optional[Dict]) -> bool:
    """判断本次写入的目标行是否就是当前登录用户本人。

    Args:
        row_identity: 目标行身份字典（如 {"name": "张三"}），
            由 BaseService.update_by_field 传入匹配字段值；
            update() 等无法确定目标行的路径传 None（从严不放行）。

    Returns:
        bool: 目标行确为当前登录用户时返回 True
    """
    if not row_identity:
        return False
    current = get_user_name()
    if not current:
        return False
    return any(
        str(row_identity.get(key, "")) == current for key in _IDENTITY_FIELDS
    )


def enforce_write(
    table_name: str,
    fields: Optional[Dict] = None,
    action: str = "写入",
    row_identity: Optional[Dict] = None,
) -> None:
    """写操作前置守卫：不满足规则时抛出 PermissionDeniedError

    Args:
        table_name: 目标表名
        fields: 本次写入的字段字典（更新场景传入，创建场景可传 None）
        action: 操作描述（"新增"/"更新"/"删除"），用于区分创建初值与更新流转
        row_identity: 目标行身份（更新场景，BaseService 尽量提供），
            用于自助豁免的行级校验

    Raises:
        PermissionDeniedError: 当前登录角色无权执行该写操作
    """
    role = get_user_role()
    # 无上下文：脚本/测试/初始化等可信场景，放行
    if role is None:
        return
    # 管理员及以上：全部放行
    if role in ADMIN_ROLES:
        return

    if table_name in ADMIN_WRITE_TABLES:
        # 自助豁免：仅写自助字段（如修改密码），且目标行是本人时放行
        if fields and set(fields.keys()) <= SELF_SERVICE_FIELDS:
            if _is_self_service(row_identity):
                return
            raise PermissionDeniedError(
                f"权限不足：{action}表「{table_name}」只能由本人修改"
                f"（目标：{row_identity}，当前用户：{get_user_name()}）"
            )
        raise PermissionDeniedError(
            f"权限不足：{action}表「{table_name}」需要管理员及以上权限（当前角色：{role}）"
        )

    if not fields:
        return

    # 规则2：字段级保护（仅更新/删除场景；创建时的初始指派放行）
    if action != "新增":
        hit = ADMIN_WRITE_FIELDS.intersection(fields.keys())
        if hit:
            names = ", ".join(sorted(hit))
            raise PermissionDeniedError(
                f"权限不足：{action}「{names}」等管理权字段需要管理员及以上权限（当前角色：{role}）"
            )

    # 规则3：审批决定值保护（按写入值判断，创建/提交初值放行）
    for field in ADMIN_DECISION_FIELDS.intersection(fields.keys()):
        value = fields.get(field)
        if value is not None and str(value) in ADMIN_DECISION_VALUES:
            raise PermissionDeniedError(
                f"权限不足：{action}「{field}」为审批决定（{value}）需要管理员及以上权限（当前角色：{role}）"
            )
