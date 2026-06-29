"""试剂入库页面

试剂入库功能的UI页面，仅负责用户交互和数据展示，所有业务逻辑调用business/inventory_service.py中的函数。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from business.inventory_service import inventory_service
from components.sidebar_nav import render_sidebar

# 纯度选项（从业务需求定义）
PURITY_OPTIONS = ["分析纯", "化学纯", "优级纯", "色谱纯", "光谱纯", "电子纯", "工业纯"]

def main():
    st.set_page_config(page_title="试剂入库", layout="wide")
    st.title("📦 试剂入库")

    # 使用统一的侧边栏导航
    render_sidebar()

    # 获取下拉框数据源
    _result = inventory_service.get_available_chemical_names()
    chemical_names = _result.data if _result.is_success() else []
    _result = inventory_service.get_available_suppliers()
    supplier_names = _result.data if _result.is_success() else []
    _result = inventory_service.get_available_storage_locations()
    storage_location_names = _result.data if _result.is_success() else []

    # 获取试剂类型选项（从业务层获取）
    _result = inventory_service.get_available_reagent_types()
    reagent_type_names = _result.data if _result.is_success() else []
    if not reagent_type_names:
        reagent_type_names = ["普通固体试剂", "普通液体试剂", "胶体试剂/培养基", "标准品", "气体钢瓶", "生化试剂"]

    # 化学品名称到CAS号的映射（同时使用display_name作为备选匹配）
    name_to_cas = {}
    for name in chemical_names:
        _info_result = inventory_service.get_chemical_info_by_name(name)
        info = _info_result.data if _info_result.is_success() else None
        if info:
            if info.get("cas_number"):
                name_to_cas[name] = info["cas_number"]
                # 同时添加display_name作为备选键
                if info.get("display_name") and info["display_name"] != name:
                    name_to_cas[info["display_name"]] = info["cas_number"]

    # ========== 入库表单区域 ==========
    st.subheader("➕ 新建入库记录")
    
    if not chemical_names:
        st.warning("⚠️ 化学品信息表为空，请先在【化学品信息管理】中添加化学品")
        if st.button("跳转到化学品信息管理", type="primary"):
            st.switch_page("pages/7_化学品信息管理.py")
        st.stop()

    with st.form("inventory_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_name = st.selectbox(
                "试剂名称*",
                options=[""] + chemical_names,
                index=0,
                help="必须从下拉列表中选择已有化学品"
            )
            
            # 获取CAS号，支持多种匹配方式
            cas_value = name_to_cas.get(selected_name, "")
            if not cas_value and selected_name:
                # 尝试去除空格匹配
                cas_value = name_to_cas.get(selected_name.strip(), "")
                if not cas_value:
                    # 尝试直接查询
                    _info_result = inventory_service.get_chemical_info_by_name(selected_name)
                    info = _info_result.data if _info_result.is_success() else None
                    cas_value = info.get("cas_number", "") if info else ""
            
            st.text_input(
                "CAS号",
                value=cas_value,
                disabled=True,
                help="根据选择的试剂名称自动匹配，不可修改"
            )
            
            remaining_qty = st.number_input(
                "剩余量(g)*",
                min_value=0.001,
                step=0.001,
                value=500.0,
                help="当前试剂瓶中的实际剩余量（新入库默认为满量，应等于规格）"
            )
            
            spec = st.number_input(
                "规格(g)*",
                min_value=0.001,
                step=0.001,
                value=500.0,
                help="试剂瓶的标称规格（入库时默认满量）"
            )

        with col2:
            # 纯度下拉框，默认选中"分析纯"
            purity_index = PURITY_OPTIONS.index("分析纯") if "分析纯" in PURITY_OPTIONS else 0
            purity = st.selectbox(
                "纯度*",
                options=PURITY_OPTIONS,
                index=purity_index,
                help="选择试剂纯度等级"
            )
            
            # 试剂类型下拉框，默认选中"普通固体试剂"
            reagent_type_index = reagent_type_names.index("普通固体试剂") if "普通固体试剂" in reagent_type_names else 0
            reagent_type = st.selectbox(
                "试剂类型*",
                options=reagent_type_names,
                index=reagent_type_index,
                help="选择试剂类型"
            )
            
            unit_price = st.number_input(
                "采购单价(元)",
                min_value=0.0,
                step=0.01,
                help="该试剂的采购单价"
            )
            
            supplier = st.selectbox(
                "供应商",
                options=[""] + supplier_names,
                index=0,
                help="选择供应商，或输入新供应商"
            )
            
            production_date = st.date_input("生产日期")
            
            storage_location = st.selectbox(
                "存储位置",
                options=[""] + storage_location_names,
                index=0,
                help="选择存储位置，或输入新位置"
            )

        # 检查剩余量是否超过规格
        if remaining_qty > spec:
            st.warning("⚠️ 剩余量超过规格，可能输入有误")

        submitted = st.form_submit_button("确认入库", type="primary", use_container_width=True)

        if submitted:
            if not selected_name:
                st.error("请选择试剂名称")
            elif not cas_value:
                st.error("CAS号不能为空，请检查化学品信息表")
            else:
                result = inventory_service.create_inventory_record(
                    reagent_name=selected_name,
                    cas_number=cas_value,
                    remaining_quantity=remaining_qty,
                    specification=spec,
                    purity=purity,
                    reagent_type=reagent_type,
                    unit_price=unit_price if unit_price > 0 else None,
                    supplier=supplier if supplier else None,
                    production_date=str(production_date),
                    storage_location=storage_location if storage_location else None
                )

                if result.is_success():
                    st.success(result.message)
                    st.rerun()
                else:
                    st.error(result.message)

if __name__ == "__main__":
    main()
