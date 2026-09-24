"""认证模块

提供统一的登录认证和权限检查功能。
所有页面通过此模块进行用户身份验证和权限控制。

安全特性：
- 密码使用 PBKDF2-HMAC-SHA256（600k 迭代）加盐哈希存储，从不存明文（utils/password_utils）
- 登录失败锁定：连续 5 次失败后临时锁定 15 分钟（防暴力破解）
- 会话超时：默认 30 分钟无操作自动登出（config.settings.SESSION_TIMEOUT_MINUTES）
- 迁移期老账户（password_hash 为空）首次登录使用默认初始密码，登录后提示尽快修改
"""
import datetime
import time

import streamlit as st
from config.settings import SESSION_TIMEOUT_MINUTES, DEFAULT_INITIAL_PASSWORD
from business.permission_service import permission_service
from services.base.person_service import person_service
from utils.password_utils import verify_password

# 登录安全策略
MAX_LOGIN_ATTEMPTS = 5      # 连续失败次数上限
LOCKOUT_MINUTES = 15        # 锁定分钟数
MIN_PASSWORD_LENGTH = 6     # 最小密码长度


def _register_login_failure() -> None:
    """记录一次登录失败，达到阈值则临时锁定账户"""
    st.session_state["login_attempts"] = st.session_state.get("login_attempts", 0) + 1
    if st.session_state["login_attempts"] >= MAX_LOGIN_ATTEMPTS:
        st.session_state["login_locked_until"] = (
            datetime.datetime.now() + datetime.timedelta(minutes=LOCKOUT_MINUTES)
        )
        st.error(f"账户已被临时锁定，请 {LOCKOUT_MINUTES} 分钟后再试")
    else:
        remaining = MAX_LOGIN_ATTEMPTS - st.session_state["login_attempts"]
        st.error(f"用户名或密码错误，还剩 {remaining} 次尝试机会")


def render_login_form():
    """渲染登录表单

    在 app.py 和所有页面中调用，当用户未登录时显示登录界面。
    登录成功后设置 st.session_state 中的用户信息。

    登录流程：
    1. 验证用户存在于 person 表中，并校验密码（PBKDF2 哈希比对，
       迁移期老账户可用默认初始密码首次登录）
    2. 验证用户角色权限
    3. 失败累计达 5 次则锁定 15 分钟
    """
    st.markdown("## 登录")

    # 初始化登录失败计数与锁定状态
    if "login_attempts" not in st.session_state:
        st.session_state["login_attempts"] = 0
    if "login_locked_until" not in st.session_state:
        st.session_state["login_locked_until"] = None

    # 锁定检查
    locked_until = st.session_state["login_locked_until"]
    if locked_until is not None:
        now = datetime.datetime.now()
        if now < locked_until:
            remaining_minutes = int((locked_until - now).total_seconds() / 60) + 1
            st.error(f"账户已被临时锁定，请 {remaining_minutes} 分钟后再试")
            return False
        # 锁定时间已过，重置计数
        st.session_state["login_attempts"] = 0
        st.session_state["login_locked_until"] = None

    with st.form("login_form", clear_on_submit=False):
        user_name = st.text_input(
            "用户名", placeholder="请输入您的姓名", key="login_user_name"
        )
        password = st.text_input(
            "密码", type="password", placeholder="请输入密码", key="login_password"
        )
        submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

        if not submitted:
            return False

        if not user_name or not user_name.strip():
            st.error("请输入用户名")
            return False
        if not password:
            st.error("请输入密码")
            return False

        user_name = user_name.strip()

        # 1. 用户名 + 密码校验（含迁移期默认初始密码）
        auth_result = person_service.authenticate(user_name, password)
        if auth_result.is_failure():
            _register_login_failure()
            return False

        # 2. 角色权限校验
        perm_result = permission_service.check_permission(user_name, "user")
        if not (perm_result.is_success() and perm_result.data):
            _register_login_failure()
            return False

        # 3. 登录成功：重置计数并写入会话
        st.session_state["login_attempts"] = 0
        st.session_state["login_locked_until"] = None
        st.session_state["logged_in"] = True
        st.session_state["user_name"] = user_name
        st.session_state["is_admin"] = bool(permission_service.is_admin(user_name).data)
        st.session_state["user_role"] = permission_service.get_user_role(user_name).data or "user"
        st.session_state["last_activity"] = time.time()
        st.success(f"欢迎，{user_name}！")
        st.rerun()

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
            "user": "普通用户",
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
                elif len(new_pw) < MIN_PASSWORD_LENGTH:
                    st.error(f"新密码至少 {MIN_PASSWORD_LENGTH} 位")
                else:
                    result = person_service.set_password(user_name, new_pw)
                    if result.is_success():
                        st.success("密码已更新")
                    else:
                        st.error(result.message or "密码更新失败")

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

    必须在 require_auth() 之后调用。

    Returns:
        bool: 当前用户是否为管理员
    """
    if not st.session_state.get("logged_in", False):
        return False

    if not st.session_state.get("is_admin", False):
        st.error("权限不足：此功能仅限管理员使用")
        return False

    return True


def require_super_admin():
    """要求超级管理员权限

    必须在 require_auth() 之后调用。

    Returns:
        bool: 当前用户是否为超级管理员
    """
    if not st.session_state.get("logged_in", False):
        return False

    if st.session_state.get("user_role", "user") != "super_admin":
        st.error("权限不足：此功能仅限超级管理员使用")
        return False

    return True


def require_teacher():
    """要求教师及以上权限（教师、管理员、超级管理员）

    必须在 require_auth() 之后调用。

    Returns:
        bool: 当前用户是否为教师及以上角色
    """
    if not st.session_state.get("logged_in", False):
        return False

    if st.session_state.get("user_role", "user") not in {"super_admin", "admin", "teacher"}:
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
