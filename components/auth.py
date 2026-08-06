"""认证模块

提供统一的登录认证和权限检查功能。
所有页面通过此模块进行用户身份验证和权限控制。

安全性：使用 PBKDF2-HMAC-SHA256 密码哈希，密码从不以明文存储。
"""
import datetime

import streamlit as st
from business.permission_service import permission_service
from services.base.person_service import person_service


def render_login_form():
    """渲染登录表单

    在 app.py 和所有页面中调用，当用户未登录时显示登录界面。
    登录成功后设置 st.session_state 中的用户信息。

    登录流程：
    1. 验证用户存在于 person 表中
    2. 验证密码（PBKDF2-HMAC-SHA256 哈希比对）
    3. 验证用户角色权限
    """
    st.markdown("## 登录")

    # 初始化登录失败计数
    if "login_attempts" not in st.session_state:
        st.session_state["login_attempts"] = 0
    if "login_locked_until" not in st.session_state:
        st.session_state["login_locked_until"] = None

    # 检查是否被锁定
    if st.session_state["login_locked_until"] is not None:
        now = datetime.datetime.now()
        if now < st.session_state["login_locked_until"]:
            remaining_minutes = int((st.session_state["login_locked_until"] - now).total_seconds() / 60) + 1
            st.error(f"账户已被临时锁定，请{remaining_minutes}分钟后再试")
            return False
        else:
            # 锁定时间已过，重置计数
            st.session_state["login_attempts"] = 0
            st.session_state["login_locked_until"] = None

    with st.form("login_form", clear_on_submit=False):
        user_name = st.text_input("用户名", placeholder="请输入您的姓名", key="login_user_name")
        password = st.text_input("密码", type="password", placeholder="请输入密码", key="login_password")
        submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

        if submitted:
            if not user_name or not user_name.strip():
                st.error("请输入用户名")
                return False

            if not password:
                st.error("请输入密码")
                return False

            user_name = user_name.strip()

            # 1. 验证密码
            auth_result = person_service.authenticate(user_name, password)
            if auth_result.is_failure():
                st.session_state["login_attempts"] += 1
                # 连续失败 5 次后锁定 15 分钟
                if st.session_state["login_attempts"] >= 5:
                    st.session_state["login_locked_until"] = datetime.datetime.now() + datetime.timedelta(minutes=15)
                    st.error("账户已被临时锁定，请15分钟后再试")
                else:
                    remaining = 5 - st.session_state["login_attempts"]
                    st.error(f"用户名或密码错误，还剩{remaining}次尝试机会")
                return False

            # 2. 验证权限
            has_permission, msg = permission_service.check_permission(user_name, "user")
            if not has_permission:
                st.session_state["login_attempts"] += 1
                if st.session_state["login_attempts"] >= 5:
                    st.session_state["login_locked_until"] = datetime.datetime.now() + datetime.timedelta(minutes=15)
                    st.error("账户已被临时锁定，请15分钟后再试")
                else:
                    st.error(msg)
                return False

            # 3. 登录成功 - 重置计数
            st.session_state["login_attempts"] = 0
            st.session_state["login_locked_until"] = None
            st.session_state["logged_in"] = True
            st.session_state["user_name"] = user_name
            user_role = permission_service.get_user_role(user_name)
            is_admin = permission_service.is_admin(user_name)
            st.session_state["is_admin"] = is_admin
            st.session_state["user_role"] = user_role
            st.success(f"欢迎，{user_name}！")
            st.rerun()

    return False


def require_auth():
    """要求用户认证

    在每个页面的 main() 函数开头调用。
    如果用户未登录，渲染登录表单并阻止页面内容显示。

    Returns:
        bool: 用户是否已认证
    """
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        render_login_form()
        return False

    # 显示当前用户信息和登出按钮
    with st.sidebar:
        st.divider()
        user_name = st.session_state.get("user_name", "未知")
        user_role = st.session_state.get("user_role", "user")
        role_labels = {
            "super_admin": "超级管理员",
            "admin": "管理员",
            "teacher": "教师",
            "user": "普通用户"
        }
        role_label = role_labels.get(user_role, "普通用户")
        st.caption(f"当前用户：{user_name}（{role_label}）")
        if st.button("登出", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state.pop("user_name", None)
            st.session_state.pop("is_admin", None)
            st.session_state.pop("user_role", None)
            st.rerun()

    return True


def require_admin():
    """要求管理员权限（包含超级管理员）

    在需要管理员权限的页面/功能中调用。
    必须在 require_auth() 之后调用。

    Returns:
        bool: 当前用户是否为管理员
    """
    if not st.session_state.get("logged_in", False):
        return False

    is_admin = st.session_state.get("is_admin", False)
    if not is_admin:
        st.error("权限不足：此功能仅限管理员使用")
        return False

    return True


def require_super_admin():
    """要求超级管理员权限

    在需要超级管理员权限的页面/功能中调用。
    必须在 require_auth() 之后调用。

    Returns:
        bool: 当前用户是否为超级管理员
    """
    if not st.session_state.get("logged_in", False):
        return False

    user_role = st.session_state.get("user_role", "user")
    if user_role != "super_admin":
        st.error("权限不足：此功能仅限超级管理员使用")
        return False

    return True


def require_teacher():
    """要求教师及以上权限（教师、管理员、超级管理员）

    在需要教师权限的页面/功能中调用。
    必须在 require_auth() 之后调用。

    Returns:
        bool: 当前用户是否为教师及以上角色
    """
    if not st.session_state.get("logged_in", False):
        return False

    user_role = st.session_state.get("user_role", "user")
    if user_role not in {"super_admin", "admin", "teacher"}:
        st.error("权限不足：此功能仅限教师及以上角色使用")
        return False

    return True


def get_current_user() -> str:
    """获取当前登录用户名

    Returns:
        当前用户名，未登录时返回空字符串
    """
    return st.session_state.get("user_name", "")


def is_logged_in() -> bool:
    """检查用户是否已登录

    Returns:
        True 表示已登录
    """
    return st.session_state.get("logged_in", False)