"""试剂库管理系统 - 主应用入口（首页）

使用 Streamlit 原生多页面应用（MPA）方案：
- 本文件为系统首页，启动命令：streamlit run app.py
- pages/ 目录下的文件由 Streamlit 自动生成侧边栏导航
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from config.settings import SYSTEM_NAME, VERSION
from business.dashboard_service import dashboard_service
from components.sidebar_nav import render_sidebar
from datetime import date

st.set_page_config(
    page_title=f"{SYSTEM_NAME} - 首页",
    page_icon="🧪",
    layout="wide"
)

# 侧边栏系统信息（导航由 Streamlit 自动生成）
render_sidebar()

# 主页面内容
st.title(f"🧪 {SYSTEM_NAME}")
st.subheader("实验室试剂库存管理系统")
st.markdown("#### 高效管理 · 安全可控 · 数据透明")
st.divider()

# 功能卡片区域
st.markdown("### 🎯 快速入口")
col1, col2, col3 = st.columns(3)

with col1:
    with st.container(border=True):
        st.markdown("### 📦 实时库存")
        st.markdown("查看当前所有试剂的库存状态")
        st.page_link("pages/1_实时库存.py", label="进入", icon="📦", use_container_width=True)

with col2:
    with st.container(border=True):
        st.markdown("### ➕ 试剂入库")
        st.markdown("将新试剂录入系统")
        st.page_link("pages/2_试剂入库.py", label="进入", icon="➕", use_container_width=True)

with col3:
    with st.container(border=True):
        st.markdown("### 📤 领用归还")
        st.markdown("试剂领用和归还操作")
        st.page_link("pages/3_领用归还.py", label="进入", icon="📤", use_container_width=True)

col4, col5, col6 = st.columns(3)

with col4:
    with st.container(border=True):
        st.markdown("### 🔍 综合查询")
        st.markdown("多条件查询试剂和历史记录")
        st.page_link("pages/4_综合查询.py", label="进入", icon="🔍", use_container_width=True)

with col5:
    with st.container(border=True):
        st.markdown("### 📊 数据看板")
        st.markdown("统计报表和可视化图表")
        st.page_link("pages/5_数据看板.py", label="进入", icon="📊", use_container_width=True)

with col6:
    with st.container(border=True):
        st.markdown("### 🧪 化学品信息")
        st.markdown("管理化学品基础信息")
        st.page_link("pages/7_化学品信息管理.py", label="进入", icon="🧪", use_container_width=True)

col7, col8, col9 = st.columns(3)

with col7:
    with st.container(border=True):
        st.markdown("### 📋 管控化学品目录")
        st.markdown("查看管控化学品名录")
        st.page_link("pages/8_管控化学品目录.py", label="进入", icon="📋", use_container_width=True)

with col8:
    with st.container(border=True):
        st.markdown("### ⚙️ 系统设置")
        st.markdown("系统配置和数据查看")
        st.page_link("pages/6_系统设置.py", label="进入", icon="⚙️", use_container_width=True)

st.divider()

# 快速统计
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

# 系统说明
st.divider()
st.markdown(f"**版本**: {VERSION} | **更新日期**: {date.today().strftime('%Y-%m-%d')}")
st.markdown("**系统功能**: 试剂入库、领用、归还、查询、统计、过期判断")
