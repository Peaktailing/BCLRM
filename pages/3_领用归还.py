"""领用归还页面

实现试剂领用和归还功能，包含必填字段和可选字段，显示成功或失败提示。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from business.borrow_service import reagent_borrow, get_all_borrow_users, get_latest_borrow_record
from business.return_service import reagent_return
from business.query_service import get_all_reagents, filter_reagents
from components.sidebar_nav import render_sidebar
from utils.error_handler import logger

def main():
    """主函数：领用归还页面"""
    st.set_page_config(page_title="领用归还", layout="wide")
    st.title("📤 试剂领用/归还")
    
    # 使用统一的侧边栏导航
    render_sidebar(current_page="领用归还")
    
    # 标签切换
    tab1, tab2 = st.tabs(["📥 试剂领用", "📤 试剂归还"])
    
    # 领用标签
    with tab1:
        st.subheader("试剂领用")
        
        if "borrow_cart" not in st.session_state:
            st.session_state.borrow_cart = []
        
        st.markdown("#### 搜索试剂")
        
        col_search, col_filter = st.columns([2, 1])
        with col_search:
            search_keyword = st.text_input("搜索试剂", placeholder="输入试剂名称、CAS号或编号...")
        with col_filter:
            show_only_borrowable = st.checkbox("只显示可借", value=True)
        
        # 使用业务层统一过滤方法
        display_reagents = filter_reagents(
            keyword=search_keyword if search_keyword else None,
            borrowable_only=show_only_borrowable,
        )
        
        if display_reagents:
            cart_bottle_numbers = [item["bottle_number"] for item in st.session_state.borrow_cart]
            
            table_data = []
            for reagent in display_reagents:
                is_in_cart = reagent.bottle_number in cart_bottle_numbers
                status_color = "🟢" if reagent.borrowable_flag == "可借" else "🔵" if reagent.borrowable_flag == "已借出" else "🔴"
                table_data.append({
                    "选择": is_in_cart,
                    "编号": reagent.bottle_number,
                    "名称": reagent.reagent_name or "-",
                    "CAS号": reagent.cas_number or "-",
                    "剩余量": f"{reagent.remaining_quantity}g" if reagent.remaining_quantity else "-",
                    "规格": f"{reagent.specification}g" if reagent.specification else "-",
                    "纯度": reagent.purity or "-",
                    "状态": f"{status_color} {reagent.borrowable_flag}" if reagent.borrowable_flag else "-",
                    "存储位置": reagent.storage_location or "-",
                    "_bottle_number": reagent.bottle_number
                })
            
            edited_data = st.data_editor(
                table_data,
                column_config={
                    "选择": st.column_config.CheckboxColumn(
                        "选择",
                        default=False,
                    ),
                    "_bottle_number": None
                },
                hide_index=True,
                use_container_width=True,
                num_rows="dynamic",
                key="reagent_table"
            )
            
            # 添加选中的试剂到购物车（使用按钮确认，避免频繁更新）
            selected_bottles = [row["_bottle_number"] for row in edited_data if row["选择"]]
            if selected_bottles:
                if st.button(f"添加 {len(selected_bottles)} 瓶试剂到领用清单", use_container_width=True):
                    for bottle_number in selected_bottles:
                        if bottle_number not in cart_bottle_numbers:
                            reagent = next(r for r in display_reagents if r.bottle_number == bottle_number)
                            st.session_state.borrow_cart.append({
                                "bottle_number": reagent.bottle_number,
                                "reagent_name": reagent.reagent_name,
                                "cas_number": reagent.cas_number,
                                "specification": reagent.specification,
                                "remaining_quantity": reagent.remaining_quantity
                            })
                    st.success(f"已添加 {len(selected_bottles)} 瓶试剂到领用清单")
        
        else:
            st.info("没有找到匹配的试剂")
        
        if st.session_state.borrow_cart:
            st.markdown("---")
            st.subheader(f"📋 领用清单 ({len(st.session_state.borrow_cart)} 瓶)")
            
            col1, col2 = st.columns([3, 1])
            with col1:
                table_data = []
                for idx, item in enumerate(st.session_state.borrow_cart, 1):
                    table_data.append({
                        "序号": idx,
                        "编号": item["bottle_number"],
                        "名称": item["reagent_name"] or "-",
                        "CAS号": item["cas_number"] or "-",
                        "规格": f"{item['specification']}g" if item["specification"] else "-",
                        "剩余量": f"{item['remaining_quantity']}g" if item["remaining_quantity"] else "-",
                        "删除": "🗑️"
                    })
                
                edited_cart = st.data_editor(
                    table_data,
                    column_config={
                        "删除": st.column_config.TextColumn(
                            "操作",
                            disabled=False,
                            width="small"
                        )
                    },
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key="cart_table"
                )
                
                # 删除操作
                for row in edited_cart:
                    if row["删除"] != "🗑️":
                        st.session_state.borrow_cart = [
                            item for item in st.session_state.borrow_cart 
                            if item["bottle_number"] != row["编号"]
                        ]
            
            with col2:
                if st.button("清空清单", use_container_width=True):
                    st.session_state.borrow_cart = []
            
            st.markdown("---")
            
            # 领用人下拉选择（从业务层获取）
            user_list = get_all_borrow_users()
            
            col_user, col_submit = st.columns([2, 1])
            with col_user:
                user = st.selectbox(
                    "领用人*",
                    options=[""] + user_list,
                    placeholder="选择或输入领用人",
                    key="borrow_user_select"
                )
            
            with col_submit:
                # 确认领用按钮 - 直接提交，不需要二次确认
                if st.button("确认领用", type="primary", use_container_width=True):
                    if not user:
                        st.error("请选择或输入领用人")
                    else:
                        logger.info(f"[页面] 确认领用按钮被点击，购物车数量: {len(st.session_state.borrow_cart)}")
                        success_count = 0
                        fail_messages = []
                        
                        for item in st.session_state.borrow_cart:
                            logger.debug(f"[页面] 正在领用试剂瓶: {item['bottle_number']}")
                            success, msg = reagent_borrow(
                                bottle_number=item["bottle_number"],
                                user=user,
                                borrow_qty=item["remaining_quantity"] or 0.1
                            )
                            logger.debug(f"[页面] 领用结果: {success}, {msg}")
                            if success:
                                success_count += 1
                            else:
                                fail_messages.append(f"{item['bottle_number']}: {msg}")
                        
                        if success_count == len(st.session_state.borrow_cart):
                            st.success(f"✅ 全部领用成功！共领用 {success_count} 瓶试剂")
                            st.session_state.borrow_cart = []
                        else:
                            st.warning(f"⚠️ 部分领用成功：{success_count}/{len(st.session_state.borrow_cart)}")
                            for msg in fail_messages:
                                st.error(msg)
        
        else:
            st.markdown("---")
            st.info("请从上方表格中选择要领用的试剂，已选试剂会添加到领用清单中")
    
    # 归还标签
    with tab2:
        st.subheader("试剂归还")
        
        # 获取已借出和耗尽的试剂（都可以归还）- 使用业务层统一过滤方法
        borrowed_reagents = filter_reagents(status=["已借出", "耗尽"])
        
        if borrowed_reagents:
            # 选择试剂瓶
            reagent_options = [(f"{r.bottle_number} - {r.reagent_name or '未知'} ({r.borrowable_flag})", r) 
                              for r in borrowed_reagents]
            
            selected_reagent = st.selectbox(
                "选择已借出的试剂瓶*", 
                options=[opt[1] for opt in reagent_options],
                format_func=lambda x: f"{x.bottle_number} - {x.reagent_name or '未知'} ({x.borrowable_flag})",
                key="return_reagent_select"
            )
            
            # 获取最近的借出记录（从业务层获取）
            latest_record = get_latest_borrow_record(selected_reagent.bottle_number)
            default_borrow_user = ""
            if latest_record:
                default_borrow_user = latest_record.user or ""
            
            # 归还人（默认是借出人，但可修改）
            return_user = st.text_input(
                "归还人*", 
                value=default_borrow_user,
                help="默认是借出人，可修改"
            )
            
            # 剩余量滑块输入
            st.markdown("#### 归还时剩余量")
            col_slider, col_value = st.columns([3, 1])
            
            with col_slider:
                # 获取试剂规格作为最大值
                max_qty = selected_reagent.specification or 500.0
                remaining_percent = st.slider(
                    "剩余量百分比",
                    min_value=0.0,
                    max_value=100.0,
                    value=100.0,
                    step=1.0,
                    format="%.1f%%",
                    key="return_slider"
                )
            
            with col_value:
                remaining_qty = (remaining_percent / 100) * max_qty
                st.metric(
                    label="剩余量(g)",
                    value=f"{remaining_qty:.2f}"
                )
            
            # 确认归还按钮
            if st.button("确认归还", type="primary", use_container_width=True):
                if not return_user:
                    st.error("请填写归还人")
                else:
                    success, msg = reagent_return(
                        bottle_number=selected_reagent.bottle_number,
                        return_user=return_user,
                        remaining_qty=remaining_qty
                    )
                    if success:
                        st.success(msg)
                        # 重新加载页面
                        st.rerun()
                    else:
                        st.error(msg)
        
        else:
            st.info("当前没有已借出的试剂")

if __name__ == "__main__":
    main()
