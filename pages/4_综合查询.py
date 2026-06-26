"""综合查询页面

提供多条件查询功能，支持查询试剂信息、领用历史和归还历史。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from business.query_service import search_reagents, get_borrow_history, get_return_history
from components.sidebar_nav import render_sidebar

def main():
    """主函数：综合查询页面"""
    st.set_page_config(page_title="综合查询", layout="wide")
    st.title("🔍 综合查询")
    
    # 使用统一的侧边栏导航
    render_sidebar(current_page="综合查询")
    
    # 标签切换
    tab1, tab2, tab3 = st.tabs(["🧪 试剂查询", "📥 领用历史", "📤 归还历史"])
    
    # 试剂查询标签
    with tab1:
        st.subheader("试剂查询")
        
        # 查询条件
        col1, col2, col3 = st.columns(3)
        with col1:
            bottle_number = st.number_input("试剂瓶编号", min_value=0, step=1, help="精确匹配")
            bottle_number = bottle_number if bottle_number > 0 else None
        with col2:
            reagent_name = st.text_input("试剂名称", help="模糊匹配")
        with col3:
            cas_number = st.text_input("CAS号", help="精确匹配")
        
        col4, col5 = st.columns(2)
        with col4:
            supplier = st.text_input("供应商", help="模糊匹配")
        with col5:
            borrowable_only = st.checkbox("只显示可借", help="勾选后只显示可借状态的试剂")
        
        # 查询按钮
        if st.button("查询", type="primary", use_container_width=True):
            results = search_reagents(
                bottle_number=bottle_number,
                reagent_name=reagent_name,
                cas_number=cas_number,
                supplier=supplier,
                borrowable_only=borrowable_only
            )
            
            # 显示结果
            if results:
                table_data = []
                for reagent in results:
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
                        "供应商": reagent.supplier or "-",
                        "状态": f"{status_color} {reagent.borrowable_flag}" if reagent.borrowable_flag else "-"
                    })
                
                st.dataframe(table_data, use_container_width=True, hide_index=True)
                st.success(f"找到 {len(results)} 条记录")
            else:
                st.info("没有找到匹配的试剂")
    
    # 领用历史标签
    with tab2:
        st.subheader("领用历史查询")
        
        col1, col2 = st.columns(2)
        with col1:
            bottle_number = st.number_input("试剂瓶编号", min_value=0, step=1, key="borrow_bottle")
            bottle_number = bottle_number if bottle_number > 0 else None
        with col2:
            user = st.text_input("领用人")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("查询领用记录", type="primary", use_container_width=True):
                results = get_borrow_history(bottle_number=bottle_number, user=user)
                
                if results:
                    st.dataframe(results, use_container_width=True)
                    st.success(f"找到 {len(results)} 条领用记录")
                else:
                    st.info("没有找到领用记录")
        with col_btn2:
            if st.button("查询全部", use_container_width=True):
                results = get_borrow_history()
                
                if results:
                    st.dataframe(results, use_container_width=True)
                    st.success(f"找到 {len(results)} 条领用记录")
                else:
                    st.info("没有找到领用记录")
    
    # 归还历史标签
    with tab3:
        st.subheader("归还历史查询")
        
        col1, col2 = st.columns(2)
        with col1:
            bottle_number = st.number_input("试剂瓶编号", min_value=0, step=1, key="return_bottle")
            bottle_number = bottle_number if bottle_number > 0 else None
        with col2:
            user = st.text_input("归还人")
        
        if st.button("查询归还记录", type="primary", use_container_width=True):
            results = get_return_history(bottle_number=bottle_number, user=user)
            
            if results:
                st.dataframe(results, use_container_width=True)
                st.success(f"找到 {len(results)} 条归还记录")
            else:
                st.info("没有找到归还记录")

if __name__ == "__main__":
    main()