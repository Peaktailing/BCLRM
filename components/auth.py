"""认证模块 - Streamlit 登录/权限控制

提供统一的登录表单、会话管理、权限检查功能。
"""
import streamlit as st
from services.base.person_service import person_service
from business.permission_service import (
    can_view, can_add_reagent, can_edit_reagent, can_delete_reagent,
    can_borrow, can_approve, can_approve_bottle,
    can_manage_users, can_system_settings,
    get_role_label, PERMISSION_MATRIX,
)


# ── 会话状态 Key ──────────────────────────────────────────

SESSION_KEY_USER = "auth_user"
SESSION_KEY_LOGGED_IN = "auth_logged_in"


# ── 初始化 ────────────────────────────────────────────────

def init_auth():
    """初始化认证状态"""
    if SESSION_KEY_LOGGED_IN not in st.session_state:
        st.session_state[SESSION_KEY_LOGGED_IN] = False
    if SESSION_KEY_USER not in st.session_state:
        st.session_state[SESSION_KEY_USER] = None


def get_user() -> dict | None:
    """获取当前登录用户"""
    return st.session_state.get(SESSION_KEY_USER)


def is_logged_in() -> bool:
    """是否已登录"""
    return st.session_state.get(SESSION_KEY_LOGGED_IN, False)


def get_role() -> str:
    """获取当前用户角色，未登录返回 student"""
    user = get_user()
    return user.get("role", "student") if user else "student"


def get_user_id() -> str | None:
    """获取当前用户 user_id"""
    user = get_user()
    return user.get("user_id") if user else None


# ── 登录/登出 ─────────────────────────────────────────────

def render_login_form():
    """渲染登录表单，返回 True 表示登录成功"""
    st.markdown("## 🧪 试剂库管理系统")
    st.markdown("### 系统登录")
    st.markdown("请输入工号和密码进行身份验证")

    with st.form("login_form", clear_on_submit=False):
        work_id = st.text_input("工号", placeholder="如: zhang, wang, root")
        password = st.text_input("密码", type="password", placeholder="默认: 123456")
        submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

        if submitted:
            if not work_id.strip():
                st.error("请输入工号")
                return False
            user = person_service.authenticate(work_id.strip(), password.strip() or "123456")
            if user:
                st.session_state[SESSION_KEY_USER] = dict(user)
                st.session_state[SESSION_KEY_LOGGED_IN] = True
                st.rerun()
            else:
                st.error("工号或密码错误")
                return False

    # 快捷测试账号
    with st.expander("💡 测试账号"):
        st.markdown("""
        | 角色 | 工号 | 密码 | 手机号 |
        |------|------|------|--------|
        | 超级管理员 | root | SysAdmin@2024 | 13800000001 |
        | 管理员(张) | zhang | Zhang@1234 | 13800000002 |
        | 管理员(李) | li | LiManager@12 | 13800000003 |
        | 教师(王教授) | wang | Wang@1234 | 13800000004 |
        | 教师(赵教授) | zhao | Zhao@1234 | 13800000005 |
        | 学生(小学生) | stu1 | Student@12 | 13800000006 |
        | 学生(中学生) | stu2 | Student@12 | 13800000007 |
        """)

    return False


def render_logout_button():
    """渲染登出按钮"""
    user = get_user()
    if user:
        name = user.get("display_name", user.get("name", ""))
        role_label = get_role_label(user.get("role", ""))
        st.markdown(f"**当前用户**: {name} ({role_label})")

    if st.button("🚪 退出登录", use_container_width=True):
        st.session_state[SESSION_KEY_USER] = None
        st.session_state[SESSION_KEY_LOGGED_IN] = False
        st.rerun()


# ── 权限检查 ──────────────────────────────────────────────

def require_login():
    """要求登录，未登录则显示登录页并阻止后续代码"""
    if not is_logged_in():
        render_login_form()
        return False
    return True


def check_perm(perm_fn, *args, **kwargs) -> tuple:
    """执行权限检查，返回 (ok, message)"""
    role = get_role()
    return perm_fn(role, *args, **kwargs)


def require_perm(perm_fn, *args, error_msg: str = None, **kwargs):
    """要求权限，无权限时显示警告"""
    ok, msg = check_perm(perm_fn, *args, **kwargs)
    if not ok:
        st.warning(f"⛔ {error_msg or msg}")
    return ok


def get_user_permissions() -> dict:
    """获取当前角色的权限摘要"""
    role = get_role()
    result = {}
    for action, perm_map in PERMISSION_MATRIX.items():
        result[action] = perm_map.get(role, "❌")
    return result


# ── 侧边栏认证信息 ────────────────────────────────────────

def render_auth_sidebar():
    """在侧边栏渲染认证信息和权限矩阵"""
    if is_logged_in():
        user = get_user()
        st.success(f"已登录: {user.get('display_name', user.get('name'))}")
        st.caption(f"角色: {get_role_label(user.get('role', ''))} | 部门: {user.get('department', '')}")

        # 显示从属管理员
        if user.get("role") in ("teacher", "student"):
            admins = person_service.get_admins_for_user(user.get("user_id"))
            if admins:
                admin_names = "、".join([a.get("display_name", a.get("name", "")) for a in admins])
                st.caption(f"从属管理员: {admin_names}")

        render_logout_button()
    else:
        st.info("未登录（学生权限）")
        st.caption("仅可查看试剂库存")

    st.divider()

    # 权限矩阵
    with st.expander("📋 权限矩阵", expanded=False):
        perms = get_user_permissions()
        for action, val in perms.items():
            st.caption(f"{action}: {val}")