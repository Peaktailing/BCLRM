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
from utils.user_context import get_user_role

# 角色层级：super_admin > admin > teacher > user
ADMIN_ROLES = {"admin", "super_admin"}

# 规则1：整表写保护 —— 这些表的任何写操作都要求管理员及以上
#   person          用户与密码/角色管理
#   controlled_list 管控化学品名录（页面只读，仅数据维护时开放）
ADMIN_WRITE_TABLES = {
    "person",
    "controlled_list",
}

# 规则2：字段级写保护 —— 任何表写入这些字段都要求管理员及以上
#   approval_status 审批状态流转（待审批→已批准/已驳回）
#   领用归还、课程用量等普通操作不碰该字段，不会被误伤
ADMIN_WRITE_FIELDS = {
    "approval_status",
}


def enforce_write(table_name: str, fields: Optional[Dict] = None, action: str = "写入") -> None:
    """写操作前置守卫：不满足规则时抛出 PermissionDeniedError

    Args:
        table_name: 目标表名
        fields: 本次写入的字段字典（更新场景传入，创建场景可传 None）
        action: 操作描述，用于错误提示

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
        raise PermissionDeniedError(
            f"权限不足：{action}表「{table_name}」需要管理员及以上权限（当前角色：{role}）"
        )

    if fields and ADMIN_WRITE_FIELDS.intersection(fields.keys()):
        hit = ", ".join(sorted(ADMIN_WRITE_FIELDS.intersection(fields.keys())))
        raise PermissionDeniedError(
            f"权限不足：{action}「{hit}」等审批字段需要管理员及以上权限（当前角色：{role}）"
        )
