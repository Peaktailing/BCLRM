"""认证模块 - Streamlit 登录/权限控制

四层权限体系：
- super_admin: 系统数据维护，所有页面
- admin: 管理自己试剂瓶，审批借出，所有页面
- teacher: 除系统设置外所有页面
- student: 仅查看库存（无需登录，一键进入）
"""
import streamlit as st
from services.base.person_service import person_service
from business.permission_service import (
    can_view, can_add_reagent, can_edit_reagent, can_delete_reagent,
    can_borrow, can_approve, can_approve_bottle,
    can_manage_users, can_system_settings,
    get_role_label, PERMISSION_MATRIX, ROLE_LEVELS, ROLE_LABELS,
)

SESSION_KEY_USER = "auth_user"
SESSION_KEY_LOGGED_IN = "auth_logged_in"


def init_auth():
    """初始化认证状态"""
    if SESSION_KEY_LOGGED_IN not in st.session_state:
        st.session_state[SESSION_KEY_LOGGED_IN] = False
    if SESSION_KEY_USER not in st.session_state:
        st.session_state[SESSION_KEY_USER] = None


def get_user() -> dict | None:
    return st.session_state.get(SESSION_KEY_USER)


def is_logged_in() -> bool:
    return st.session_state.get(SESSION_KEY_LOGGED_IN, False)


def get_role() -> str:
    user = get_user()
    return user.get("role", "student") if user else "student"


def get_user_id() -> str | None:
    user = get_user()
    return user.get("user_id") if user else None


def do_login(user: dict):
    """执行登录"""
    st.session_state[SESSION_KEY_USER] = dict(user)
    st.session_state[SESSION_KEY_LOGGED_IN] = True


def do_student_login():
    """学生快速登录（空用户）"""
    st.session_state[SESSION_KEY_USER] = {"role": "student", "display_name": "访客", "name": "访客", "department": ""}
    st.session_state[SESSION_KEY_LOGGED_IN] = True


def render_login_form():
    """渲染登录表单"""
    st.markdown("## 🧪 试剂库管理系统")
    st.markdown("### 系统登录")

    # 学生快速入口
    col_s, col_l = st.columns([1, 2])
    with col_s:
        if st.button("🎓 学生/访客入口", use_container_width=True, type="secondary",
                     help="无需登录，仅查看试剂库存"):
            do_student_login()
            st.rerun()

    with col_l:
        with st.form("login_form", clear_on_submit=False):
            work_id = st.text_input("工号", placeholder="如: zhang, wang, root")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

            if submitted:
                if not work_id.strip():
                    st.error("请输入工号")
                    return False
                if not password:
                    st.error("请输入密码")
                    return False
                user = person_service.authenticate(work_id.strip(), password)
                if user:
                    do_login(user)
                    st.rerun()
                else:
                    st.error("工号或密码错误")
                    return False

    # 测试账号
    with st.expander("💡 测试账号"):
        st.markdown("""
        | 角色 | 工号 | 密码 |
        |------|------|------|
        | 超级管理员 | root | SysAdmin@2024 |
        | 管理员(张) | zhang | Zhang@1234 |
        | 管理员(李) | li | LiManager@12 |
        | 教师(王教授) | wang | Wang@1234 |
        | 教师(赵教授) | zhao | Zhao@1234 |
        | 学生(小学生) | stu1 | Student@12 |
        | 学生(中学生) | stu2 | Student@12 |
        """)
    return False


def render_logout_button():
    """登出按钮"""
    user = get_user()
    if user:
        name = user.get("display_name", user.get("name", ""))
        role_label = get_role_label(user.get("role", ""))
        st.markdown(f"**{name}** ({role_label})")
    if st.button("🚪 退出登录", use_container_width=True):
        st.session_state[SESSION_KEY_USER] = None
        st.session_state[SESSION_KEY_LOGGED_IN] = False
        st.rerun()


def require_login():
    """登录守卫"""
    if not is_logged_in():
        render_login_form()
        return False
    return True


def check_perm(perm_fn, *args, **kwargs) -> tuple:
    role = get_role()
    return perm_fn(role, *args, **kwargs)


def require_perm(perm_fn, *args, error_msg: str = None, **kwargs):
    ok, msg = check_perm(perm_fn, *args, **kwargs)
    if not ok:
        st.warning(f"⛔ {error_msg or msg}")
    return ok


def get_user_permissions() -> dict:
    role = get_role()
    result = {}
    for action, perm_map in PERMISSION_MATRIX.items():
        result[action] = perm_map.get(role, "❌")
    return result


def render_auth_sidebar():
    """侧边栏认证信息"""
    if is_logged_in():
        user = get_user()
        st.success(f"已登录: {user.get('display_name', user.get('name'))}")
        st.caption(f"角色: {get_role_label(user.get('role', ''))} | 部门: {user.get('department', '')}")
        if user.get("role") in ("teacher", "student"):
            admins = person_service.get_admins_for_user(user.get("user_id") or "")
            if admins:
                admin_names = "、".join([a.get("display_name", a.get("name", "")) for a in admins])
                st.caption(f"从属管理员: {admin_names}")
        render_logout_button()
    else:
        st.info("未登录")

    st.divider()
    with st.expander("📋 权限矩阵", expanded=False):
        perms = get_user_permissions()
        for action, val in perms.items():
            st.caption(f"{action}: {val}")