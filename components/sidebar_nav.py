"""侧边栏导航组件

提供统一的侧边栏导航功能，所有页面共用。
"""
import streamlit as st
from config.settings import SYSTEM_NAME, VERSION


def render_sidebar(current_page: str = None):
    """
    渲染统一的侧边栏导航

    参数：
        current_page: 当前页面名称（可选，用于高亮显示）
    """
    with st.sidebar:
        st.title(f"🧪 {SYSTEM_NAME}")
        st.markdown(f"**版本：{VERSION}**")
        st.divider()

        st.markdown("### 功能导航")
        if st.button("🏠 返回首页", use_container_width=True):
            st.switch_page("pages/0_欢迎页面.py")
        if st.button("📦 实时库存", use_container_width=True):
            st.switch_page("pages/1_实时库存.py")
        if st.button("➕ 试剂入库", use_container_width=True):
            st.switch_page("pages/2_试剂入库.py")
        if st.button("📤 领用归还", use_container_width=True):
            st.switch_page("pages/3_领用归还.py")
        if st.button("🔍 综合查询", use_container_width=True):
            st.switch_page("pages/4_综合查询.py")
        if st.button("📊 数据看板", use_container_width=True):
            st.switch_page("pages/5_数据看板.py")
        if st.button("🧪 化学品信息", use_container_width=True):
            st.switch_page("pages/7_化学品信息管理.py")
        if st.button("📋 管控化学品目录", use_container_width=True):
            st.switch_page("pages/8_管控化学品目录.py")
        if st.button("⚙️ 系统设置", use_container_width=True):
            st.switch_page("pages/6_系统设置.py")

        st.divider()
