"""数据看板页面

显示库存统计、领用统计、归还统计等数据可视化信息。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import matplotlib.pyplot as plt
from business.dashboard_service import dashboard_service
from components.sidebar_nav import render_sidebar

def main():
    """主函数：数据看板页面"""
    st.set_page_config(page_title="数据看板", layout="wide")
    st.title("📊 数据看板")
    
    # 使用统一的侧边栏导航
    render_sidebar(current_page="数据看板")
    
    # 获取统计数据
    _inv_result = dashboard_service.get_inventory_stats()
    inventory_stats = _inv_result.data if _inv_result.is_success() else {}
    _borrow_result = dashboard_service.get_borrow_stats()
    borrow_stats = _borrow_result.data if _borrow_result.is_success() else {}
    _return_result = dashboard_service.get_return_stats()
    return_stats = _return_result.data if _return_result.is_success() else {}
    _supplier_result = dashboard_service.get_supplier_stats()
    supplier_stats = _supplier_result.data if _supplier_result.is_success() else {}
    _location_result = dashboard_service.get_storage_location_stats()
    location_stats = _location_result.data if _location_result.is_success() else {}
    
    # 库存统计卡片
    st.subheader("库存概览")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("试剂瓶总数", inventory_stats["total_bottles"])
    with col2:
        st.metric("可借数量", inventory_stats["borrowable"])
    with col3:
        st.metric("已借出", inventory_stats["borrowed"])
    with col4:
        st.metric("已耗尽", inventory_stats["exhausted"])
    with col5:
        st.metric("总剩余量", f"{inventory_stats['total_quantity']}g")
    
    st.divider()
    
    # 领用/归还统计
    st.subheader("领用/归还统计")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("累计领用次数", borrow_stats["total_borrows"])
    with col2:
        st.metric("累计归还次数", return_stats["total_returns"])
    
    # 领用排行
    st.subheader("领用排行（按人员）")
    if borrow_stats["user_stats"]:
        top_users = sorted(borrow_stats["user_stats"].items(), key=lambda x: x[1], reverse=True)[:5]
        users, counts = zip(*top_users) if top_users else ([], [])
        
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(users, counts, color='#4CAF50')
        ax.set_xlabel('领用人')
        ax.set_ylabel('领用次数')
        ax.set_title('领用次数排行')
        plt.xticks(rotation=45)
        st.pyplot(fig)
    else:
        st.info("暂无领用数据")
    
    # 供应商统计
    st.subheader("试剂分布（按供应商）")
    if supplier_stats:
        suppliers = list(supplier_stats.keys())
        counts = list(supplier_stats.values())
        
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.pie(counts, labels=suppliers, autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
        st.pyplot(fig)
    else:
        st.info("暂无供应商数据")
    
    # 存储位置统计
    st.subheader("存储位置分布")
    if location_stats:
        locations = list(location_stats.keys())
        counts = list(location_stats.values())
        
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.barh(locations, counts, color='#2196F3')
        ax.set_xlabel('试剂瓶数量')
        ax.set_ylabel('存储位置')
        ax.set_title('各位置试剂瓶数量')
        st.pyplot(fig)
    else:
        st.info("暂无存储位置数据")

if __name__ == "__main__":
    main()