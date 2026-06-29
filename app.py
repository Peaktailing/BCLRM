"""试剂库管理系统 - 主应用入口（首页）

使用 Streamlit 原生多页面应用（MPA）方案：
- 本文件为系统首页，启动命令：streamlit run app.py
- pages/ 目录下的文件由 Streamlit 自动生成侧边栏导航

四层权限体系：
- 超级管理员 (super_admin): 系统数据维护，无借出/审批
- 管理员 (admin): 管理自己试剂瓶，审批自己瓶的借出
- 教师 (teacher): 可借出试剂
- 学生 (student): 仅查看（未登录默认学生）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from config.settings import SYSTEM_NAME, VERSION
from business.dashboard_service import dashboard_service
from business.seed_permission import init_permission_system
from components.auth import (
    init_auth, is_logged_in, get_user, get_role, get_role_label,
    render_login_form, render_auth_sidebar,
    check_perm, can_borrow, can_add_reagent, can_manage_users, can_system_settings,
)
from datetime import date

# ── 页面配置 ──────────────────────────────────────────────

st.set_page_config(
    page_title=f"{SYSTEM_NAME} - 首页",
    page_icon="🧪",
    layout="wide",
)

# ── 初始化 ────────────────────────────────────────────────

init_auth()
init_permission_system()

# ── 未登录 → 显示登录页 ──────────────────────────────────

if not is_logged_in():
    # 居中登录表单
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        render_login_form()
    st.stop()

# ── 已登录 → 显示首页 ────────────────────────────────────

user = get_user()
role = get_role()
role_label = get_role_label(role)

# 侧边栏
render_auth_sidebar()

# 主页面
st.title(f"🧪 {SYSTEM_NAME}")
st.subheader("实验室试剂库存管理系统")
st.markdown(
    f"#### 高效管理 · 安全可控 · 数据透明  "
    f"| 欢迎，**{user.get('display_name', user.get('name'))}** "
    f"({role_label})"
)
st.divider()

# ── 功能卡片（根据权限显示） ──────────────────────────────

st.markdown("### 🎯 快速入口")

# 第一行
cards_row1 = [
    ("📦 实时库存", "查看当前所有试剂的库存状态", "pages/1_实时库存.py", True),  # 所有人可见
    ("➕ 试剂入库", "将新试剂录入系统", "pages/2_试剂入库.py", can_add_reagent(role)[0]),
    ("📤 领用归还", "试剂领用和归还操作", "pages/3_领用归还.py", can_borrow(role)[0]),
]
col1, col2, col3 = st.columns(3)
for col, (title, desc, link, allowed) in zip([col1, col2, col3], cards_row1):
    with col:
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.markdown(desc)
            if allowed:
                st.page_link(link, label="进入", icon=title[:2], use_container_width=True)
            else:
                st.caption("⛔ 无权限")

# 第二行
cards_row2 = [
    ("🔍 综合查询", "多条件查询试剂和历史记录", "pages/4_综合查询.py", True),
    ("📊 数据看板", "统计报表和可视化图表", "pages/5_数据看板.py", True),
    ("🧪 化学品信息", "管理化学品基础信息", "pages/7_化学品信息管理.py", can_manage_users(role)[0]),
]
col4, col5, col6 = st.columns(3)
for col, (title, desc, link, allowed) in zip([col4, col5, col6], cards_row2):
    with col:
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.markdown(desc)
            if allowed:
                st.page_link(link, label="进入", icon=title[:2], use_container_width=True)
            else:
                st.caption("⛔ 无权限")

# 第三行
cards_row3 = [
    ("📋 管控化学品目录", "查看管控化学品名录", "pages/8_管控化学品目录.py", True),
    ("👥 人员管理", "管理用户和权限", "pages/9_人员管理.py", can_manage_users(role)[0]),
    ("⚙️ 系统设置", "系统配置和数据查看", "pages/6_系统设置.py", can_system_settings(role)[0]),
]
col7, col8, col9 = st.columns(3)
for col, (title, desc, link, allowed) in zip([col7, col8, col9], cards_row3):
    if not title:
        continue
    with col:
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.markdown(desc)
            if allowed:
                st.page_link(link, label="进入", icon=title[:2], use_container_width=True)
            else:
                st.caption("⛔ 无权限")

st.divider()

# ── 快速统计 ──────────────────────────────────────────────

try:
    result = dashboard_service.get_inventory_stats()
    stats = result.data if result.is_success() else {}
    st.markdown("### 📊 库存概览")
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    stat_col1.metric("试剂瓶总数", stats.get("total_bottles", 0))
    stat_col2.metric("可借数量", stats.get("borrowable", 0))
    stat_col3.metric("已借出", stats.get("borrowed", 0))
    stat_col4.metric("已耗尽", stats.get("exhausted", 0))
except Exception:
    st.info("暂无法获取库存统计数据")

# ── 系统说明 ──────────────────────────────────────────────

st.divider()
st.markdown(f"**版本**: {VERSION} | **更新日期**: {date.today().strftime('%Y-%m-%d')}")
st.markdown("**系统功能**: 试剂入库、领用、归还、查询、统计、过期判断")
st.markdown(f"**当前用户**: {user.get('display_name', '')} ({role_label}) | **权限等级**: {role_label}")