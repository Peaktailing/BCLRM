"""试剂库管理系统 - 主应用入口（页面路由器）

使用 Streamlit 原生多页面应用（MPA）v2：st.navigation + st.Page 动态构建导航。

权限规则：
- 未登录：隐藏导航栏，仅显示登录表单（此时各业务页均未注册，URL 直达也会被拒绝）
- 已登录：注册各业务页面；「系统设置」仅超级管理员可见，
  非超级管理员既看不到该栏目，也无法通过 URL 直达（未注册的页面会被拒绝并回到默认页）

启动命令：streamlit run app.py
"""
import streamlit as st
from config.settings import SYSTEM_NAME
from components.auth import is_logged_in, render_login_form
from db.database import db

st.set_page_config(
    page_title=SYSTEM_NAME,
    page_icon="🧪",
    layout="wide"
)


@st.cache_resource
def _ensure_database():
    """启动时确保数据库表结构与迁移为最新（幂等，仅执行一次）

    避免因新增字段未迁移导致相关功能（如领用量写入）失败。
    """
    db.init_tables()


_ensure_database()


def _login_page():
    """未登录时展示的登录页"""
    st.markdown(f"## 🧪 {SYSTEM_NAME}")
    st.markdown("请先登录后使用系统。")
    render_login_form()


# ---------- 页面定义（路径相对入口文件）----------
_home_page = st.Page("views/0_首页.py", title="首页", icon="🏠", default=True)

_common_pages = [
    st.Page("views/1_实时库存.py", title="实时库存", icon="📦"),
    st.Page("views/2_试剂入库.py", title="试剂入库", icon="➕"),
    st.Page("views/3_领用归还.py", title="领用归还", icon="📤"),
    st.Page("views/4_综合查询.py", title="综合查询", icon="🔍"),
    st.Page("views/5_数据看板.py", title="数据看板", icon="📊"),
    st.Page("views/9_学期用量.py", title="学期用量", icon="📈"),
    st.Page("views/10_课程管理.py", title="课程管理", icon="📚"),
    st.Page("views/11_采购管理.py", title="采购管理", icon="🧾"),
    st.Page("views/12_待报废与过期预警.py", title="待报废与过期预警", icon="🗑️"),
    st.Page("views/7_化学品信息管理.py", title="化学品信息管理", icon="🧪"),
    st.Page("views/8_管控化学品目录.py", title="管控化学品目录", icon="📋"),
]

_settings_page = st.Page("views/6_系统设置.py", title="系统设置", icon="⚙️")


if not is_logged_in():
    # 未登录：隐藏导航组件，仅渲染登录页
    st.navigation(
        [st.Page(_login_page, title="登录", icon="🔑")],
        position="hidden"
    ).run()
else:
    pages = [_home_page] + _common_pages
    # 仅超级管理员注册「系统设置」页面
    if st.session_state.get("user_role") == "super_admin":
        pages.append(_settings_page)
    st.navigation(pages).run()
