"""实时库存页面

显示当前试剂库存状态，支持快速查看和筛选。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from business.query_service import query_service
from components.sidebar_nav import render_sidebar

def main():
    """主函数：实时库存页面"""
    st.set_page_config(page_title="实时库存", layout="wide")
    st.title("📦 实时库存")
    
    # 使用统一的侧边栏导航
    render_sidebar(current_page="实时库存")
    
    # 获取所有试剂
    result = query_service.get_all_reagents()
    reagents = result.data if result.is_success() else []
    
    # 统计信息
    total_count = len(reagents)
    borrowable_count = sum(1 for r in reagents if r.borrowable_flag == "可借")
    exhausted_count = sum(1 for r in reagents if r.borrowable_flag == "耗尽")
    
    # 统计卡片
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("试剂瓶总数", total_count)
    with col2:
        st.metric("可借数量", borrowable_count)
    with col3:
        st.metric("已耗尽", exhausted_count)
    
    st.divider()
    
    # 获取所有试剂名称用于模糊匹配
    reagent_names = sorted(set(r.reagent_name for r in reagents if r.reagent_name))
    
    # 搜索筛选 - 支持模糊匹配候选项
    selected_name = st.selectbox(
        "搜索试剂名称（模糊匹配）",
        options=[""] + reagent_names,
        index=0,
        help="输入关键词可模糊匹配试剂名称"
    )
    
    # 状态筛选
    status_filter = st.selectbox("状态筛选", ["全部", "可借", "已借出", "耗尽"])
    
    # 额外的文本搜索（支持CAS号、编号等）
    extra_search = st.text_input("额外搜索（CAS号/编号）")
    
    # 使用业务层统一过滤方法
    status_param = None if status_filter == "全部" else status_filter
    _filter_result = query_service.filter_reagents(
        keyword=extra_search if extra_search else None,
        reagent_name=selected_name if selected_name else None,
        status=status_param,
        borrowable_only=False,
    )
    filtered_reagents = _filter_result.data if _filter_result.is_success() else []
    
    # 显示试剂列表
    if filtered_reagents:
        # 准备表格数据
        table_data = []
        for reagent in filtered_reagents:
            status_color = {
                "可借": "🟢",
                "已借出": "🔵",
                "耗尽": "🔴"
            }.get(reagent.borrowable_flag, "⚪")
            
            table_data.append({
                "编号": reagent.bottle_number,
                "名称": reagent.reagent_name or "-",
                "CAS号": reagent.cas_number or "-",
                "剩余量": f"{reagent.remaining_quantity}g" if reagent.remaining_quantity else "-",
                "规格": f"{reagent.specification}g" if reagent.specification else "-",
                "纯度": reagent.purity or "-",
                "启封日期": reagent.unseal_date or "-",
                "过期状态": reagent.expired_flag or "正常",
                "状态": f"{status_color} {reagent.borrowable_flag}" if reagent.borrowable_flag else "-",
                "存储位置": reagent.storage_location or "-"
            })
        
        # 显示表格
        st.dataframe(table_data, use_container_width=True, hide_index=True)
    else:
        st.info("没有找到匹配的试剂")

if __name__ == "__main__":
    main()