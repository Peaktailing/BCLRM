"""认证模块

提供统一的登录认证和权限检查功能。
所有页面通过此模块进行用户身份验证和权限控制。
"""
import streamlit as st
from business.permission_service import permission_service


def render_login_form():
    """渲染登录表单

    在 app.py 和所有页面中调用，当用户未登录时显示登录界面。
    登录成功后设置 st.session_state 中的用户信息。
    """
    st.markdown("## 登录")

    with st.form("login_form", clear_on_submit=False):
        user_name = st.text_input("用户名", placeholder="请输入您的姓名", key="login_user_name")
        submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

        if submitted:
            if not user_name or not user_name.strip():
                st.error("请输入用户名")
                return False

            user_name = user_name.strip()
            has_permission, msg = permission_service.check_permission(user_name, "user")

            if has_permission:
                st.session_state["logged_in"] = True
                st.session_state["user_name"] = user_name
                # 检查是否为管理员
                is_admin = permission_service.is_admin(user_name)
                st.session_state["is_admin"] = is_admin
                st.session_state["user_role"] = "admin" if is_admin else "user"
                st.success(f"欢迎，{user_name}！")
                st.rerun()
            else:
                st.error(msg)
                return False

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
        role_label = "管理员" if user_role == "admin" else "普通用户"
        st.caption(f"当前用户：{user_name}（{role_label}）")
        if st.button("登出", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state.pop("user_name", None)
            st.session_state.pop("is_admin", None)
            st.session_state.pop("user_role", None)
            st.rerun()

    return True


def require_admin():
    """要求管理员权限

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