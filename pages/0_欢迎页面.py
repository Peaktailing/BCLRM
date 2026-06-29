"""欢迎页面 - 系统首页

系统主入口页面，提供功能导航和快速入口。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from config.settings import SYSTEM_NAME, VERSION
from business.dashboard_service import dashboard_service
from components.sidebar_nav import render_sidebar
from datetime import date

def main():
    """主函数：欢迎页面"""
    st.set_page_config(
        page_title=f"{SYSTEM_NAME} - 首页",
        page_icon="🧪",
        layout="wide"
    )
    
    # 使用统一的侧边栏导航
    render_sidebar(current_page="欢迎页面")
    
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
            if st.button("进入", key="inv", use_container_width=True):
                st.switch_page("pages/1_实时库存.py")
    
    with col2:
        with st.container(border=True):
            st.markdown("### ➕ 试剂入库")
            st.markdown("将新试剂录入系统")
            if st.button("进入", key="add", use_container_width=True):
                st.switch_page("pages/2_试剂入库.py")
    
    with col3:
        with st.container(border=True):
            st.markdown("### 📤 领用归还")
            st.markdown("试剂领用和归还操作")
            if st.button("进入", key="borrow", use_container_width=True):
                st.switch_page("pages/3_领用归还.py")
    
    col4, col5, col6 = st.columns(3)
    
    with col4:
        with st.container(border=True):
            st.markdown("### 🔍 综合查询")
            st.markdown("多条件查询试剂和历史记录")
            if st.button("进入", key="query", use_container_width=True):
                st.switch_page("pages/4_综合查询.py")
    
    with col5:
        with st.container(border=True):
            st.markdown("### 📊 数据看板")
            st.markdown("统计报表和可视化图表")
            if st.button("进入", key="dashboard", use_container_width=True):
                st.switch_page("pages/5_数据看板.py")
    
    with col6:
        with st.container(border=True):
            st.markdown("### 🧪 化学品信息")
            st.markdown("管理化学品基础信息")
            if st.button("进入", key="chemical", use_container_width=True):
                st.switch_page("pages/7_化学品信息管理.py")
    
    col7 = st.columns(1)[0]
    with col7:
        with st.container(border=True):
            st.markdown("### ⚙️ 系统设置")
            st.markdown("系统配置和权限管理")
            if st.button("进入", key="settings", use_container_width=True):
                st.switch_page("pages/6_系统设置.py")
    
    st.divider()
    
    # 快速统计
    try:
        result = dashboard_service.get_inventory_stats()
        stats = result.data if result.is_success() else {}
        st.markdown("### 📊 库存概览")
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        stat_col1.metric("试剂瓶总数", stats["total_bottles"])
        stat_col2.metric("可借数量", stats["borrowable"])
        stat_col3.metric("已借出", stats["borrowed"])
        stat_col4.metric("已耗尽", stats["exhausted"])
    except Exception as e:
        st.info("暂无法获取库存统计数据")
    
    # 系统说明
    st.divider()
    st.markdown("---")
    st.markdown(f"**版本**: {VERSION} | **更新日期**: {date.today().strftime('%Y-%m-%d')}")
    st.markdown("**系统功能**: 试剂入库、领用、归还、查询、统计")

if __name__ == "__main__":
    main()