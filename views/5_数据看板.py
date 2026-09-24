"""数据看板页面

显示库存统计、领用统计、归还统计等数据可视化信息。
"""
import streamlit as st
import pandas as pd
from business.dashboard_service import dashboard_service
from business.expiry_service import expiry_service
from components.sidebar_nav import render_sidebar
from components.auth import require_auth

def main():
    """主函数：数据看板页面"""
    st.set_page_config(page_title="数据看板", layout="wide")
    st.title("📊 数据看板")
    
    # 认证检查
    if not require_auth():
        st.stop()
    
    # 使用统一的侧边栏导航
    render_sidebar()

    # 进入看板时刷新一次过期状态（重新计算并写库，保证看板数据为最新）
    with st.spinner("正在刷新过期状态…"):
        _sync_result = expiry_service.sync_all()
    if _sync_result.is_success():
        st.caption(f"🔄 已刷新过期状态（本次更新 {_sync_result.data or 0} 瓶）")

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
        st.metric("试剂瓶总数", inventory_stats.get("total_bottles", 0))
    with col2:
        st.metric("可借数量", inventory_stats.get("borrowable", 0))
    with col3:
        st.metric("已借出", inventory_stats.get("borrowed", 0))
    with col4:
        st.metric("已耗尽", inventory_stats.get("exhausted", 0))
    with col5:
        st.metric("总剩余量", f"{inventory_stats.get('total_quantity', 0)}g")
    
    st.divider()

    # 过期状态概览
    st.subheader("过期状态概览")
    _expiry_result = expiry_service.get_expiry_stats()
    expiry_stats = _expiry_result.data if _expiry_result.is_success() else {}
    ec1, ec2, ec3 = st.columns(3)
    with ec1:
        st.metric("✅ 正常", expiry_stats.get("normal", 0))
    with ec2:
        st.metric("⚠️ 即将过期", expiry_stats.get("expiring", 0))
    with ec3:
        st.metric("❌ 已过期", expiry_stats.get("expired", 0))
    
    st.divider()
    
    # 领用/归还统计
    st.subheader("领用/归还统计")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("累计领用次数", borrow_stats.get("total_borrows", 0))
    with col2:
        st.metric("累计归还次数", return_stats.get("total_returns", 0))
    
    # 领用排行
    st.subheader("领用排行（按人员）")
    if borrow_stats.get("user_stats"):
        top_users = sorted(borrow_stats["user_stats"].items(), key=lambda x: x[1], reverse=True)[:5]
        df_users = pd.DataFrame(top_users, columns=['领用人', '领用次数'])
        st.bar_chart(df_users, x='领用人', y='领用次数', color='#4CAF50', use_container_width=True)
    else:
        st.info("暂无领用数据")
    
    # 供应商统计
    st.subheader("试剂分布（按供应商）")
    if supplier_stats:
        df_suppliers = pd.DataFrame(list(supplier_stats.items()), columns=['供应商', '数量'])
        st.bar_chart(df_suppliers, x='供应商', y='数量', color='#FF9800', use_container_width=True)
    else:
        st.info("暂无供应商数据")
    
    # 存储位置统计
    st.subheader("存储位置分布")
    if location_stats:
        df_locations = pd.DataFrame(list(location_stats.items()), columns=['存储位置', '数量'])
        st.bar_chart(df_locations, x='存储位置', y='数量', color='#2196F3', use_container_width=True)
    else:
        st.info("暂无存储位置数据")

if __name__ == "__main__":
    main()
