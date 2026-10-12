"""当前登录用户上下文（服务端权限守卫的数据源）

登录成功后由 components/auth.py 写入，登出时清除。
db/base_service.py 的写操作守卫据此判断当前操作者角色，
确保即使页面漏做权限控制，服务端也会拦截越权写入。

使用 ContextVar 存储：Streamlit 每个会话的脚本在独立执行上下文中运行，
天然隔离不同用户的上下文，无需加锁。
"""
from contextvars import ContextVar
from typing import Dict, Optional

# None 表示「无登录上下文」：命令行脚本 / 测试 / 启动初始化等可信场景
_user_context: ContextVar[Optional[Dict]] = ContextVar("reagent_user_context", default=None)


def set_user(user_name: str, role: str) -> None:
    """写入当前登录用户（登录成功及每次页面刷新时调用）"""
    _user_context.set({"user_name": user_name, "role": role or "user"})


def clear_user() -> None:
    """清除上下文（登出/未登录时调用）"""
    _user_context.set(None)


def get_user_name() -> Optional[str]:
    """当前用户名，无上下文返回 None"""
    ctx = _user_context.get()
    return ctx.get("user_name") if ctx else None


def get_user_role() -> Optional[str]:
    """当前用户角色，无上下文返回 None"""
    ctx = _user_context.get()
    return ctx.get("role") if ctx else None
