"""认证模块

提供统一的登录认证和权限检查功能。
所有页面通过此模块进行用户身份验证和权限控制。

认证说明：
- 用户名 + 密码登录，密码以 sha256 + 随机盐哈希存储（见 utils/security）
- 迁移期老账户（password_hash 为空）首次登录使用默认初始密码，登录后请在侧边栏修改
- 登录会话带超时（见 config.settings.SESSION_TIMEOUT_MINUTES）
"""
import time
import streamlit as st
from config.settings import SESSION_TIMEOUT_MINUTES, DEFAULT_INITIAL_PASSWORD
from business.permission_service import permission_service
from services.base.person_service import person_service
from utils.security import verify_password, hash_password


def render_login_form():
    """渲染登录表单

    在 app.py 和所有页面中调用，当用户未登录时显示登录界面。
    登录成功后设置 st.session_state 中的用户信息。
    """
    st.markdown("## 登录")

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
            person = person_service.get_by_name(user_name)
            if not person:
                st.error("用户不存在，请联系管理员")
                return False

            # 密码校验
            if not person.password_hash:
                # 迁移期老账户：使用默认初始密码完成首次登录并即时落库
                if password == DEFAULT_INITIAL_PASSWORD:
                    person_service.update(person.id, {"password_hash": hash_password(password)})
                    st.info(f"首次登录成功，初始密码为 {DEFAULT_INITIAL_PASSWORD}，请尽快在侧边栏修改密码")
                else:
                    st.error(f"密码错误（首次登录请使用初始密码 {DEFAULT_INITIAL_PASSWORD}）")
                    return False
            elif not verify_password(password, person.password_hash):
                st.error("密码错误")
                return False

            # 角色权限校验
            perm_result = permission_service.check_permission(user_name, "user")
            if perm_result.is_success() and perm_result.data:
                st.session_state["logged_in"] = True
                st.session_state["user_name"] = user_name
                user_role = permission_service.get_user_role(user_name).data or "user"
                is_admin = bool(permission_service.is_admin(user_name).data)
                st.session_state["is_admin"] = is_admin
                st.session_state["user_role"] = user_role
                st.session_state["last_activity"] = time.time()
                st.success(f"欢迎，{user_name}！")
                st.rerun()
            else:
                st.error(perm_result.message or "无访问权限")
                return False

    return False


def require_auth():
    """要求用户认证

    在每个页面的 main() 函数开头调用。
    如果用户未登录或会话超时，渲染登录表单并阻止页面内容显示。

    Returns:
        bool: 用户是否已认证
    """
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    # 会话超时检查
    if st.session_state.get("logged_in"):
        last = st.session_state.get("last_activity", 0)
        if last and (time.time() - last) > SESSION_TIMEOUT_MINUTES * 60:
            st.session_state["logged_in"] = False
            st.warning(f"会话已超时（{SESSION_TIMEOUT_MINUTES} 分钟未操作），请重新登录")
            st.rerun()
        st.session_state["last_activity"] = time.time()

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

        # 修改密码
        with st.expander("修改密码"):
            old_pw = st.text_input("当前密码", type="password", key="chg_old_pw")
            new_pw = st.text_input("新密码", type="password", key="chg_new_pw")
            if st.button("保存密码", key="chg_save_pw", use_container_width=True):
                person = person_service.get_by_name(user_name)
                if not person or not verify_password(old_pw, person.password_hash or ""):
                    st.error("当前密码错误")
                elif len(new_pw) < 6:
                    st.error("新密码至少 6 位")
                else:
                    person_service.update(person.id, {"password_hash": hash_password(new_pw)})
                    st.success("密码已更新")

        if st.button("登出", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state.pop("user_name", None)
            st.session_state.pop("is_admin", None)
            st.session_state.pop("user_role", None)
            st.session_state.pop("last_activity", None)
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
