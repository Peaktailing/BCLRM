"""试剂入库页面

两种入库方式：
1. ➕ 单瓶入库：手工逐瓶录入（原有流程）
2. 📦 按采购单入库：选择「已到货」的课程采购单，按明细批量生成试剂瓶

试剂入库功能的UI页面，仅负责用户交互和数据展示，所有业务逻辑调用
business/inventory_service.py 与 business/purchase_service.py 中的函数。
"""
import streamlit as st
from business.inventory_service import inventory_service
from business.purchase_service import purchase_service
from components.sidebar_nav import render_sidebar
from components.auth import require_auth

# 纯度选项（从业务需求定义）
PURITY_OPTIONS = ["分析纯", "化学纯", "优级纯", "色谱纯", "光谱纯", "电子纯", "工业纯"]

def main():
    st.set_page_config(page_title="试剂入库", layout="wide")
    st.title("📦 试剂入库")

    # 认证检查
    if not require_auth():
        st.stop()

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

    # 管理人候选人（保管权归属）：管理员及以上；默认 = 当前登录管理员（置顶）
    _current_user = st.session_state.get("user_name", "")
    _mgr_result = inventory_service.get_available_managers()
    manager_options = _mgr_result.data if _mgr_result.is_success() else []
    if _current_user:
        manager_options = [_current_user] + [
            n for n in manager_options if n != _current_user
        ]

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

    if not chemical_names:
        st.warning("⚠️ 化学品信息表为空，请先在【化学品信息管理】中添加化学品")
        st.page_link("views/7_化学品信息管理.py", label="跳转到化学品信息管理", icon="🧪")
        st.stop()

    tab_single, tab_plan = st.tabs(["➕ 单瓶入库", "📦 按采购单入库（已到货）"])

    # ==================== 1. 单瓶入库（原有流程） ====================
    with tab_single:
        st.subheader("➕ 新建入库记录")

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

                manager = st.selectbox(
                    "管理人*",
                    options=[""] + manager_options,
                    index=1 if (
                        _current_user and manager_options
                        and manager_options[0] == _current_user
                    ) else 0,
                    help="该试剂瓶的保管人（管理人），默认为当前登录管理员；入库后其管理权归属此人，可流转给同事。"
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
                        storage_location=storage_location if storage_location else None,
                        manager=manager if manager else None
                    )

                    if result.is_success():
                        st.success(result.message)
                        _d = result.data or {}
                        if _d.get("barcode"):
                            st.session_state["last_inbound_barcode"] = _d["barcode"]
                            st.session_state["last_inbound_bottle"] = _d.get("bottle_number")
                    else:
                        st.error(result.message)

        # ---------- 🏷️ 最近一次入库的条码（可打印贴瓶） ----------
        _last_barcode = st.session_state.get("last_inbound_barcode")
        if _last_barcode:
            with st.container(border=True):
                st.subheader("🏷️ 本次入库条码")
                from utils.barcode_gen import generate_code39_png
                _png = generate_code39_png(_last_barcode)
                if _png:
                    _c_img, _c_btn = st.columns([1, 1])
                    with _c_img:
                        st.image(_png, width=360)
                    with _c_btn:
                        st.markdown(f"**条码号：`{_last_barcode}`**")
                        _last_bottle = st.session_state.get("last_inbound_bottle")
                        if _last_bottle:
                            st.caption(f"试剂瓶编号：{_last_bottle}")
                        st.download_button(
                            "🖨️ 下载条码图片（打印后贴瓶）",
                            data=_png,
                            file_name=f"barcode_{_last_barcode}.png",
                            mime="image/png",
                            key="download_inbound_barcode",
                        )
                if st.button("已打印，清除提示", key="clear_inbound_barcode"):
                    st.session_state.pop("last_inbound_barcode", None)
                    st.session_state.pop("last_inbound_bottle", None)
                    st.rerun()

    # ==================== 2. 按采购单入库（已到货） ====================
    with tab_plan:
        st.caption(
            "选择「已到货」的课程采购单，按明细批量生成试剂瓶；"
            "明细入库后回填瓶号防止重复入库，全部入库完成则采购单变为「已入库」。"
        )
        _received_plans = purchase_service.list_received_plans()
        if not _received_plans:
            st.info(
                "暂无「已到货」待入库的采购单："
                "在「采购管理 → 采购单跟踪」中把采购单标记为已到货后，可在此批量入库。"
            )
        else:
            _plan_options = {
                p.id: (
                    f"{p.plan_number}｜{p.course_name}｜{p.target_semester}"
                    f"｜{p.item_count} 条"
                )
                for p in _received_plans
            }
            _sel_plan_id = st.selectbox(
                "选择采购单",
                options=list(_plan_options.keys()),
                format_func=lambda pid: _plan_options.get(pid, str(pid)),
                key="po_inbound_plan",
            )
            _sel_plan = next(
                (p for p in _received_plans if p.id == _sel_plan_id), None
            )
            if _sel_plan:
                st.caption(
                    f"课程：{_sel_plan.course_name}｜目标学年 {_sel_plan.target_semester}"
                    f"｜状态 {_sel_plan.status}｜发起人 {_sel_plan.created_by or '—'}"
                )
                _detail = purchase_service.get_plan_detail(_sel_plan_id)
                _pending = [d for d in _detail if not d.get("bottle_number")]
                _done = [d for d in _detail if d.get("bottle_number")]

                st.dataframe(
                    [
                        {
                            "试剂名称": d["reagent_name"],
                            "CAS号": d["cas_number"] or "-",
                            "采购量": d["purchase_quantity"],
                            "供应商": d["supplier"] or "-",
                            "入库状态": (
                                f"✅ {d['bottle_number']}" if d["bottle_number"] else "⏳ 待入库"
                            ),
                        }
                        for d in _detail
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(f"待入库 {len(_pending)} 项｜已入库 {len(_done)} 项")

                _po_manager = st.selectbox(
                    "管理人*",
                    options=[""] + manager_options,
                    index=1 if (
                        _current_user and manager_options
                        and manager_options[0] == _current_user
                    ) else 0,
                    key="po_inbound_manager",
                    help="本批试剂瓶的保管人（管理人），默认为当前登录管理员。",
                )
                if st.button(
                    "📦 批量入库",
                    type="primary",
                    use_container_width=True,
                    key="po_inbound_btn",
                ):
                    if not _po_manager:
                        st.error("请选择管理人")
                    else:
                        _r = purchase_service.inbound_plan(
                            _sel_plan_id,
                            manager=_po_manager,
                            operator=_current_user,
                        )
                        if _r.is_success():
                            st.success(_r.message)
                            st.rerun()
                        else:
                            st.error(_r.message)


if __name__ == "__main__":
    main()
