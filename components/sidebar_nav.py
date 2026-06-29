"""侧边栏信息组件

提供统一的侧边栏系统信息展示。
页面导航由 Streamlit 原生多页面应用（MPA）自动生成，无需手动渲染导航按钮。
"""
import streamlit as st
from config.settings import SYSTEM_NAME, VERSION


def render_sidebar():
    """在侧边栏底部渲染系统信息（标题、版本）

    页面导航链接由 Streamlit 自动生成，显示在侧边栏顶部。
    本函数仅在侧边栏底部补充显示系统名称和版本信息。
    """
    with st.sidebar:
        st.divider()
        st.caption(f"🧪 {SYSTEM_NAME}")
        st.caption(f"版本：{VERSION}")
