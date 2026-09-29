"""领用归还页面（工单模式）

标签页：
1. 领用（发起工单）
   - 零星领用：管理员及以上可发起，不关联课程/实验
   - 课程领用：教师 + 管理员及以上可发起，需选择「课程 + 实验」
2. 还入（按工单归还）
   - 先选工单 → 勾选要归还的试剂（可多选）→ 每个填归还量

权限：还入仅限「管理员及以上」或「该工单的原领用人」。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from business.borrow_service import borrow_service
from business.work_order_service import work_order_service
from business.experiment_plan_service import experiment_plan_business
from business.query_service import query_service
from business.demand_service import demand_service
from business.allocation_service import allocation_service
from services.core.allocation_order_service import allocation_order_service
from services.core.reagent_demand_service import reagent_demand_service
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_project_service import experiment_project_service
from services.core.reagent_bottle_service import reagent_bottle_service
from services.base.experiment_item_service import experiment_item_service
from components.sidebar_nav import render_sidebar
from components.auth import require_auth
from utils.error_handler import logger

st.set_page_config(page_title="领用归还", layout="wide")

if not require_auth():
    st.stop()

render_sidebar()

st.title("📤 试剂领用 / 还入")

user_name = st.session_state.get("user_name")
user_role = st.session_state.get("user_role", "user")
is_admin = bool(st.session_state.get("is_admin", False))
is_teacher_or_above = user_role in ("super_admin", "admin", "teacher")

# 可发起的工单类型
order_types = []
if is_admin:
    order_types = ["零星领用", "课程领用"]
elif is_teacher_or_above:
    order_types = ["课程领用"]

tab_borrow, tab_approval, tab_return, tab_allocation = st.tabs([
    "📥 领用（发起工单）", "✅ 审批（管控试剂）", "📤 还入（按工单归还）", "🔀 需求调配"
])

# ==================== 1. 领用（发起工单） ====================
with tab_borrow:
    if not order_types:
        st.warning("权限不足：零星领用需管理员及以上；课程领用需教师及以上。")
    else:
        if "borrow_cart" not in st.session_state:
            st.session_state.borrow_cart = []

        order_type = st.radio(
            "工单类型", options=order_types, horizontal=True, key="wo_order_type"
        )

        # 课程领用：选择课程 + 实验
        course = None
        exp_item = None
        if order_type == "课程领用":
            col_course, col_item = st.columns(2)
            courses = experiment_course_service.get_by_semester(None)
            with col_course:
                course = st.selectbox(
                    "实验课程*",
                    options=[None] + courses,
                    format_func=lambda c: "（请选择课程）" if c is None
                    else f"{c.display_name}｜{c.teacher or ''}",
                    key="wo_course",
                )
            with col_item:
                item_options = (
                    experiment_item_service.get_by_course(course.course_name, course.semester)
                    if course else []
                )
                exp_item = st.selectbox(
                    "实验项目*",
                    options=[None] + item_options,
                    format_func=lambda x: "（请选择实验）" if x is None else x.item_name,
                    key="wo_item",
                )

                # ---------- 默认方案 / 历史工单 → 领用清单 ----------
                if course and exp_item:
                    _plan_result = experiment_plan_business.get_plan(
                        course.course_name, exp_item.item_name
                    )
                    _plan_usages = (
                        _plan_result.data.get("usages", [])
                        if _plan_result.is_success() else []
                    )

                    _status = experiment_plan_business.get_status_map().get(
                        (course.course_name, exp_item.item_name), "未领用"
                    )
                    st.caption(f"该实验当前进度：{_status}")

                    if _plan_usages:
                        # 有默认方案：按「人均用量 × 人数」加载
                        col_pcount, col_pbtn = st.columns([1, 2])
                        with col_pcount:
                            _plan_count = st.number_input(
                                "班级人数",
                                min_value=1,
                                value=course.student_count or 1,
                                step=1,
                                key="wo_plan_count",
                                help="本次默认用量 = 人均用量 × 人数",
                            )
                        with col_pbtn:
                            st.write("")
                            if st.button(
                                "📋 加载默认实验方案",
                                key="wo_load_plan",
                                use_container_width=True,
                                help="按默认用量（人均）× 人数生成清单，可再按人数或单瓶调整",
                            ):
                                _cart_result = experiment_plan_business.build_cart(
                                    course.course_name,
                                    exp_item.item_name,
                                    student_count=_plan_count,
                                )
                                if _cart_result.is_success():
                                    st.session_state.borrow_cart = _cart_result.data["cart"]
                                    st.session_state["wo_default_cart_msg"] = _cart_result.message
                                    st.rerun()
                                else:
                                    st.error(f"❌ {_cart_result.message}")
                    else:
                        # 无默认方案：回退为「按最近一次工单」生成
                        _history_order = work_order_service.find_latest_history_order(
                            course.course_name, exp_item.item_name
                        )
                        if _history_order:
                            st.caption(
                                f"📋 最近一次领用工单：{_history_order.order_number}"
                                f"（{_history_order.borrow_time or '时间未知'}）"
                            )
                            if st.button(
                                "📋 从历史工单生成默认领用清单",
                                key="wo_build_default_cart",
                                use_container_width=True,
                                help="按最近一次领用的试剂与数量预填清单，可再调整后提交",
                            ):
                                _default_result = work_order_service.build_default_cart(
                                    course.course_name, exp_item.item_name
                                )
                                if _default_result.is_success():
                                    st.session_state.borrow_cart = _default_result.data["cart"]
                                    st.session_state["wo_default_cart_msg"] = _default_result.message
                                    st.rerun()
                                else:
                                    st.error(f"❌ {_default_result.message}")
                        else:
                            st.caption(
                                "📋 该实验暂无默认方案与历史工单；"
                                "可在「课程管理 → 默认实验方案与用量」中配置"
                            )

        # 默认清单生成结果提示（一次性）
        _default_msg = st.session_state.pop("wo_default_cart_msg", None)
        if _default_msg:
            st.success(_default_msg)

        # 领用人
        _user_result = borrow_service.get_all_borrow_users()
        user_list = _user_result.data if _user_result.is_success() else []
        applicant = st.selectbox(
            "领用人*",
            options=[""] + user_list,
            placeholder="选择或输入领用人",
            key="wo_applicant",
            accept_new_options=True,
        )

        # 关联实验项目（零星领用可选）
        selected_project = None
        if order_type == "零星领用":
            _projects_all = experiment_project_service.get_all_parsed()
            if _projects_all:
                selected_project = st.selectbox(
                    "关联实验项目（可选，科研/毕设等）",
                    options=[None] + _projects_all,
                    format_func=lambda p: "（不关联项目）" if p is None else p.project_name,
                    key="wo_project",
                )

        # ---------- 搜索试剂 ----------
        st.markdown("#### 搜索试剂")
        col_search, col_filter = st.columns([2, 1])
        with col_search:
            search_keyword = st.text_input("搜索试剂", placeholder="输入试剂名称、CAS号或编号...")
        with col_filter:
            show_only_borrowable = st.checkbox("只显示可借", value=True)

        _filter_result = query_service.filter_reagents(
            keyword=search_keyword if search_keyword else None,
            borrowable_only=show_only_borrowable,
        )
        display_reagents = _filter_result.data if _filter_result.is_success() else []

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
                    "过期状态": reagent.expired_flag or "正常",
                    "状态": f"{status_color} {reagent.borrowable_flag}" if reagent.borrowable_flag else "-",
                    "存储位置": reagent.storage_location or "-",
                    "_bottle_number": reagent.bottle_number,
                })

            edited_data = st.data_editor(
                table_data,
                column_config={
                    "选择": st.column_config.CheckboxColumn("选择", default=False),
                    "_bottle_number": None,
                },
                hide_index=True,
                use_container_width=True,
                num_rows="dynamic",
                key="wo_reagent_table",
            )

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
                                "remaining_quantity": reagent.remaining_quantity,
                                "borrow_qty": reagent.remaining_quantity,
                            })
                    st.success(f"已添加 {len(selected_bottles)} 瓶试剂到领用清单")
                    st.rerun()
        else:
            st.info("没有找到匹配的试剂")

        # ---------- 领用清单 ----------
        if not st.session_state.borrow_cart:
            st.markdown("---")
            st.info("请从上方表格中选择要领用的试剂，已选试剂会添加到领用清单中")
        else:
            st.markdown("---")
            st.subheader(f"📋 领用清单 ({len(st.session_state.borrow_cart)} 瓶)")

            # 若清单来自默认方案，支持按人数整体重算
            if any(
                entry.get("qty_per_person") is not None
                for entry in st.session_state.borrow_cart
            ):
                col_rc1, col_rc2 = st.columns([1, 2])
                with col_rc1:
                    _recount = st.number_input(
                        "人数（重算）",
                        min_value=1,
                        value=int(st.session_state.borrow_cart[0].get("student_count") or 1),
                        step=1,
                        key="wo_cart_recount",
                        help="按「人均用量 × 人数」重算清单中来自默认方案的试剂用量",
                    )
                with col_rc2:
                    st.write("")
                    if st.button(
                        "🔁 按人数重算清单用量",
                        use_container_width=True,
                        key="wo_recount_btn",
                    ):
                        for entry in st.session_state.borrow_cart:
                            if entry.get("qty_per_person") is not None:
                                entry["borrow_qty"] = round(
                                    float(entry["qty_per_person"]) * _recount, 4
                                )
                                entry["student_count"] = _recount
                        st.success(f"已按 {_recount} 人重算清单用量")
                        st.rerun()

            col1, col2 = st.columns([3, 1])
            with col1:
                cart_rows = []
                for idx, entry in enumerate(st.session_state.borrow_cart, 1):
                    cart_rows.append({
                        "序号": idx,
                        "编号": entry["bottle_number"],
                        "名称": entry["reagent_name"] or "-",
                        "CAS号": entry["cas_number"] or "-",
                        "规格": f"{entry['specification']}g" if entry["specification"] else "-",
                        "剩余量": f"{entry['remaining_quantity']}g" if entry["remaining_quantity"] else "-",
                        "领用量": float(entry.get("borrow_qty") or entry.get("remaining_quantity") or 0),
                        "人均用量": (
                            float(entry["qty_per_person"])
                            if entry.get("qty_per_person") is not None else None
                        ),
                        "上次领用量": (
                            float(entry["history_qty"])
                            if entry.get("history_qty") is not None else None
                        ),
                        "删除": "🗑️",
                    })
                edited_cart = st.data_editor(
                    cart_rows,
                    column_config={
                        "领用量": st.column_config.NumberColumn(
                            min_value=0.0, step=1.0, help="本次实际领用的数量"
                        ),
                        "人均用量": st.column_config.NumberColumn(disabled=True),
                        "上次领用量": st.column_config.NumberColumn(disabled=True),
                        "删除": st.column_config.TextColumn("操作", disabled=False, width="small"),
                    },
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key="wo_cart_table",
                )
                # 回写：删除标记 + 领用量调整
                for row in edited_cart:
                    if row["删除"] != "🗑️":
                        st.session_state.borrow_cart = [
                            entry for entry in st.session_state.borrow_cart
                            if entry["bottle_number"] != row["编号"]
                        ]
                        continue
                    for entry in st.session_state.borrow_cart:
                        if entry["bottle_number"] == row["编号"]:
                            entry["borrow_qty"] = row["领用量"]
                            break
            with col2:
                if st.button("清空清单", use_container_width=True):
                    st.session_state.borrow_cart = []
                    st.rerun()

            st.markdown("---")
            if st.button("提交领用工单", type="primary", use_container_width=True):
                if not applicant:
                    st.error("请选择领用人")
                elif order_type == "课程领用" and (not course or not exp_item):
                    st.error("课程领用必须选择课程与实验项目")
                else:
                    result = work_order_service.create_order(
                        order_type=order_type,
                        applicant=applicant,
                        cart_items=st.session_state.borrow_cart,
                        course=course,
                        exp_item=exp_item,
                        created_by=user_name,
                        project_id=selected_project.id if selected_project else None,
                    )
                    if result.is_success():
                        st.success(f"✅ {result.message}")
                        st.session_state.borrow_cart = []
                        st.rerun()
                    else:
                        st.error(f"❌ {result.message}")

# ==================== 1.5 审批（管控试剂工单） ====================
with tab_approval:
    _pending_orders = work_order_service.list_pending_approvals(user_name)

    st.caption(
        "仅显示指定审批人为你的工单（含管控化学品的领用需先审批）；"
        "批准后系统自动执行领用并扣减库存，驳回则工单关闭。"
    )

    if not _pending_orders:
        st.info("暂无待你审批的工单")
    else:
        for order in _pending_orders:
            with st.expander(
                f"{order.order_number}｜{order.order_type}｜申请人 {order.applicant}"
                f"｜课程 {order.course_name or '—'}／实验 {order.item_name or '—'}",
                expanded=len(_pending_orders) <= 3,
            ):
                st.caption(f"发起时间：{order.borrow_time or '—'}")

                for item in work_order_service.get_order_items(order.id):
                    st.markdown(
                        f"- **{item['bottle_number']}**　{item['reagent_name'] or '-'}"
                        f"　领用量 {item['borrow_qty']:g}"
                    )

                _appr_remark = st.text_input(
                    "审批意见（批准/驳回原因，可选）",
                    key=f"appr_remark_{order.id}",
                )

                _c_ok, _c_no = st.columns(2)
                with _c_ok:
                    if st.button(
                        "✅ 批准并执行领用",
                        type="primary",
                        use_container_width=True,
                        key=f"appr_ok_{order.id}",
                    ):
                        _r = work_order_service.approve_order(
                            order.id, user_name, _appr_remark
                        )
                        if _r.is_success():
                            st.success(f"✅ {_r.message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {_r.message}")
                with _c_no:
                    if st.button(
                        "❌ 驳回",
                        use_container_width=True,
                        key=f"appr_no_{order.id}",
                    ):
                        _r = work_order_service.reject_order(
                            order.id, user_name, _appr_remark
                        )
                        if _r.is_success():
                            st.warning(_r.message)
                            st.rerun()
                        else:
                            st.error(f"❌ {_r.message}")

# ==================== 2. 还入（按工单归还） ====================
with tab_return:
    orders = work_order_service.list_open_orders(user_name, is_admin)

    # ---------- 扫码核验（扫瓶身条码快速核对待还信息） ----------
    with st.expander("📷 扫码核验（扫瓶身条码快速核对待还信息）", expanded=False):
        _scan_barcode = st.text_input(
            "扫描/输入条码",
            placeholder="扫码枪扫描或输入条码后回车",
            key="return_scan_barcode",
        )
        if _scan_barcode and _scan_barcode.strip():
            _scan_bc = _scan_barcode.strip()
            _scan_bottle = reagent_bottle_service.get_by_barcode(_scan_bc)
            if not _scan_bottle:
                st.warning(f"未找到条码 {_scan_bc} 对应的试剂瓶")
            else:
                _hit_order, _hit_item = None, None
                for _o in orders:
                    if not work_order_service.can_return(_o, user_name, is_admin):
                        continue
                    for _it in work_order_service.get_order_items(_o.id):
                        if (
                            _it["bottle_number"] == _scan_bottle.bottle_number
                            and _it["status"] != "已归还"
                        ):
                            _hit_order, _hit_item = _o, _it
                            break
                    if _hit_order:
                        break
                if _hit_item:
                    st.success(
                        f"✅ {_scan_bottle.bottle_number}｜{_scan_bottle.reagent_name or '-'}"
                        f"｜工单 {_hit_order.order_number}｜未还量 {_hit_item['remaining_qty']:g}"
                    )
                    st.caption("请在上方的工单下拉中选择该工单进行归还")
                else:
                    st.info(
                        f"{_scan_bottle.bottle_number}｜{_scan_bottle.reagent_name or '-'}"
                        "：没有待归还的工单记录（可能已还清或不在你的工单中）"
                    )

    if not orders:
        if is_admin:
            st.info("当前没有「借用中 / 部分归还」的工单")
        else:
            st.info("你没有待归还的工单（非管理员只能归还自己名下的工单）")
    else:
        options = {
            order.id: (
                f"{order.order_number}｜{order.order_type}｜领用人 {order.applicant}｜"
                f"{order.course_name or '—'}{('／' + order.item_name) if order.item_name else ''}｜{order.status}"
            )
            for order in orders
        }
        order_id = st.selectbox(
            "选择工单", options=list(options.keys()),
            format_func=lambda oid: options.get(oid, str(oid)),
            key="wo_return_order",
        )
        order = next((o for o in orders if o.id == order_id), None)

        if order is None:
            st.info("请选择工单")
        elif not work_order_service.can_return(order, user_name, is_admin):
            st.warning("权限不足：只有管理员及以上或该工单的原领用人可以归还")
        else:
            items = work_order_service.get_order_items(order_id)
            pending = [item for item in items if item["status"] != "已归还"]
            done_items = [item for item in items if item["status"] == "已归还"]

            st.caption(
                f"工单 {order.order_number}｜类型 {order.order_type}｜领用人 {order.applicant}"
                f"｜课程 {order.course_name or '—'}｜实验 {order.item_name or '—'}｜状态 {order.status}"
            )
            st.caption(
                f"该工单共 {len(items)} 瓶试剂：待归还 {len(pending)} 瓶，已归还 {len(done_items)} 瓶"
            )

            if not pending:
                st.info("该工单的试剂已全部归还")
            else:
                st.caption(
                    "勾选「还入」并提交后，该瓶即视为结清（不再出现在待还列表）："
                    "比例 > 0 时还回该量、差额计入实际使用量；"
                    "比例为 0 时视为空瓶，该瓶移入「试剂处置」的待报废清单。"
                    "未勾选的瓶子保持待归还。"
                )
                # 逐瓶：勾选结清 + 归还比例估算（默认 100%），还回量 = 未还量 × 比例
                return_entries = []
                for item in pending:
                    col_chk, col_info, col_slider, col_qty = st.columns([0.8, 3, 3, 2])
                    with col_chk:
                        selected = st.checkbox(
                            "还入",
                            value=True,
                            key=f"wo_ret_chk_{item['id']}",
                            label_visibility="collapsed",
                        )
                    with col_info:
                        st.markdown(
                            f"**{item['bottle_number']}**　{item['reagent_name'] or '-'}"
                        )
                        st.caption(
                            f"领用 {item['borrow_qty']:g}｜已还 {item['returned_qty']:g}"
                            f"｜未还 {item['remaining_qty']:g}"
                        )
                    with col_slider:
                        percent = st.slider(
                            "归还比例",
                            min_value=0, max_value=100, value=100, step=5,
                            key=f"wo_ret_pct_{item['id']}",
                            format="%d%%",
                            label_visibility="collapsed",
                        )
                    with col_qty:
                        qty = round(
                            float(item["remaining_qty"] or 0) * percent / 100, 4
                        )
                        if qty > 0:
                            st.metric("本次还回量", f"{qty:g}")
                        else:
                            st.metric("本次还回量", "0")
                            st.caption("空瓶 → 待报废")

                    if selected:
                        return_entries.append({
                            "item_id": item["id"],
                            "return_qty": qty,
                            "discard": qty <= 0,
                        })

                if done_items:
                    with st.expander(
                        f"已归还的试剂（{len(done_items)} 瓶）", expanded=False
                    ):
                        st.dataframe(
                            [
                                {
                                    "试剂瓶号": i["bottle_number"],
                                    "试剂名称": i["reagent_name"] or "-",
                                    "领用量": i["borrow_qty"],
                                    "已还回": i["returned_qty"],
                                    "使用量": round(
                                        float(i["borrow_qty"] or 0)
                                        - float(i["returned_qty"] or 0),
                                        4,
                                    ),
                                    "状态": i["status"],
                                }
                                for i in done_items
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )

                st.markdown("---")
                if st.button("提交归还", type="primary", use_container_width=True):
                    if not return_entries:
                        st.warning("⚠️ 请至少勾选一瓶（比例为 0% 的将作为空瓶移入待报废清单）")
                    else:
                        result = work_order_service.return_items(
                            order_id, return_entries, user_name
                        )
                        if result.is_success():
                            st.success(f"✅ {result.message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {result.message}")

# ==================== 3. 需求调配（管理员之间流转试剂） ====================
with tab_allocation:
    st.caption(
        "需求调配用于在不同管理员之间流转试剂：提交需求后，系统按"
        "「本人 → 本教研室 → 全院」智能分配，拆成若干调配单发到对应管理员手上。"
        "管理员「借出」即把试剂的管理权流转到需求人名下（自动记录一条变更历史），"
        "「退回」则驳回。现有领用 / 归还流程保持不变。"
    )

    # ---------- ① 发起需求 ----------
    st.markdown("#### ① 发起需求")
    if "dmd_lines" not in st.session_state:
        st.session_state.dmd_lines = []

    _user_result = borrow_service.get_all_borrow_users()
    _dmd_requester = st.selectbox(
        "需求人*",
        options=[""] + (_user_result.data if _user_result.is_success() else []),
        key="dmd_requester",
        help="试剂管理权将流转到此用户名下",
    )

    _reagent_result = query_service.filter_reagents(borrowable_only=True)
    _reagent_options = _reagent_result.data if _reagent_result.is_success() else []
    _reagent_labels = {
        f"{r.bottle_number}｜{r.reagent_name or '-'}"
        f"｜剩余 {(r.remaining_quantity or 0):g}": r
        for r in _reagent_options
    }
    _col_r, _col_q = st.columns([3, 1])
    with _col_r:
        _sel_label = st.selectbox(
            "选择试剂（可借）",
            options=[""] + list(_reagent_labels.keys()),
            key="dmd_reagent",
        )
    with _col_q:
        _sel_qty = st.number_input(
            "需求量", min_value=0.0, step=1.0, value=1.0, key="dmd_qty"
        )
    if st.button("➕ 加入需求清单", key="dmd_add"):
        if not _sel_label:
            st.error("请选择试剂")
        else:
            _rr = _reagent_labels[_sel_label]
            st.session_state.dmd_lines.append({
                "reagent_name": _rr.reagent_name,
                "cas_number": _rr.cas_number,
                "requested_qty": float(_sel_qty),
            })
            st.rerun()

    if st.session_state.dmd_lines:
        st.dataframe(
            [
                {
                    "试剂": line["reagent_name"],
                    "CAS号": line["cas_number"] or "-",
                    "需求量": line["requested_qty"],
                }
                for line in st.session_state.dmd_lines
            ],
            use_container_width=True,
            hide_index=True,
        )
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button("清空清单", key="dmd_clear", use_container_width=True):
                st.session_state.dmd_lines = []
                st.rerun()
        with _c2:
            if st.button(
                "提交需求", type="primary", key="dmd_submit", use_container_width=True
            ):
                if not _dmd_requester:
                    st.error("请选择需求人")
                else:
                    _res = demand_service.create_demand(
                        requester=_dmd_requester,
                        lines=st.session_state.dmd_lines,
                        created_by=user_name,
                        remark="需求调配",
                    )
                    if _res.is_success():
                        st.session_state.dmd_lines = []
                        st.success(_res.message)
                        for _s in (_res.data.get("shortages") or []):
                            st.warning(f"{_s['reagent_name']}：{_s['reason']}")
                        st.rerun()
                    else:
                        st.error(_res.message)
    else:
        st.info("需求清单为空，请先添加试剂需求")

    st.divider()

    # ---------- ② 待我处理的调配单 ----------
    st.markdown("#### ② 待我处理的调配单")
    _pending_result = demand_service.list_pending_by_manager(user_name)
    _pending_orders = _pending_result.data if _pending_result.is_success() else []
    if not _pending_orders:
        st.info("暂无待你处理的调配单")
    else:
        for _order in _pending_orders:
            _demand = reagent_demand_service.get_by_id(_order.demand_id)
            _who = _demand.requester if _demand else "—"
            _enough = "✅ 足够" if _order.is_stock_sufficient else "⚠️ 可能不足"
            with st.expander(
                f"{_order.allocation_number}｜需求人 {_who}"
                f"｜承接量 {(_order.demand_qty or 0):g}｜存量 {_enough}",
                expanded=True,
            ):
                st.caption(
                    f"智能计算：本年度需求量 {(_order.year_demand_qty or 0):g}"
                    f"｜你的可借存量 {(_order.manager_stock_qty or 0):g}"
                    f"｜全院可借存量 {(_order.total_stock_qty or 0):g}"
                )
                _items = demand_service.get_allocation_items(_order.id).data or []
                st.dataframe(
                    [
                        {
                            "试剂瓶号": i.bottle_number,
                            "试剂": i.reagent_name or "-",
                            "流转量": i.qty,
                        }
                        for i in _items
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                _cc1, _cc2 = st.columns(2)
                with _cc1:
                    if st.button(
                        "✅ 借出（管理权流转给需求人）",
                        type="primary",
                        use_container_width=True,
                        key=f"dmd_lend_{_order.id}",
                    ):
                        _r = allocation_service.handle(_order.id, "lend", user_name)
                        if _r.is_success():
                            st.success(_r.message)
                            st.rerun()
                        else:
                            st.error(_r.message)
                with _cc2:
                    if st.button(
                        "❌ 退回",
                        use_container_width=True,
                        key=f"dmd_reject_{_order.id}",
                    ):
                        _r = allocation_service.handle(_order.id, "reject", user_name)
                        if _r.is_success():
                            st.warning(_r.message)
                            st.rerun()
                        else:
                            st.error(_r.message)

    st.divider()

    # ---------- ③ 我的需求进度 ----------
    st.markdown("#### ③ 我的需求进度")
    _mine_result = demand_service.list_by_requester(user_name)
    _my_demands = _mine_result.data if _mine_result.is_success() else []
    if not _my_demands:
        st.info("你还没有提交过需求")
    else:
        for _d in _my_demands:
            _allocs = allocation_order_service.get_by_demand(_d.id)
            with st.expander(
                f"{_d.demand_number}｜{_d.status}｜{len(_allocs)} 张调配单",
                expanded=False,
            ):
                st.caption(f"需求人 {_d.requester}｜提交 {_d.borrow_time or '—'}")
                if _allocs:
                    st.dataframe(
                        [
                            {
                                "调配单": a.allocation_number,
                                "受理人": a.manager,
                                "承接量": a.demand_qty,
                                "状态": a.status,
                            }
                            for a in _allocs
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("未生成调配单（可能无可借试剂）")
