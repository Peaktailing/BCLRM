"""采购管理页面（课程 - 实验 - 试剂）

三个标签页：
1. 生成课程采购单：选课程 + 填预计人数（默认 30）→ 按人均用量预估 → 生成/覆盖
2. 采购单管理：管理员按「课程-实验」修改需求量 / 采购量
3. 汇总采购单（超管）：合并所有课程需求，统一扣减一次库存 → 最终要买多少

权限：生成 / 修改——管理员及以上；汇总——超级管理员；查看——所有登录用户。
"""
import sys
import os
import io

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from openpyxl import Workbook
from components.sidebar_nav import render_sidebar
from components.auth import require_auth
from business.purchase_service import purchase_service, DEFAULT_TARGET_STUDENT_COUNT
from business.semester_stats_service import semester_stats_service

st.set_page_config(page_title="采购管理", layout="wide")

if not require_auth():
    st.stop()

render_sidebar()

st.title("🧾 采购管理")
st.caption(
    "按「课程 - 实验 - 试剂」的人均用量预估下一学年需求："
    "人均用量 = 历史用量 ÷ 历史人数，需求 = 人均用量 × 预计人数。"
)

is_admin = bool(st.session_state.get("is_admin", False))
is_super_admin = st.session_state.get("user_role") == "super_admin"
current_user = st.session_state.get("user_name")


def _next_semester(semester: str) -> str:
    """把 2025-2026 推成 2026-2027"""
    try:
        start, end = semester.split("-")
        return f"{int(start) + 1}-{int(end) + 1}"
    except Exception:
        return ""


def _build_summary_excel(rows, semester: str) -> bytes:
    """汇总结果导出为 Excel：采购汇总 + 各课程需求明细"""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "采购汇总"
    sheet.append(["试剂名称", "CAS号", "总需求", "当前库存", "最终采购量", "供应商", "需采购"])
    for row in rows:
        sheet.append([
            row["reagent_name"],
            row["cas_number"] or "",
            row["total_demand"],
            row["current_stock"],
            row["final_purchase"],
            row["supplier"] or "",
            "是" if row["need_purchase"] else "否",
        ])

    detail_sheet = workbook.create_sheet("课程需求明细")
    detail_sheet.append(["试剂名称", "课程", "实验", "需求"])
    for row in rows:
        for demand in row["course_detail"]:
            detail_sheet.append([
                row["reagent_name"],
                demand["course_name"],
                demand["item_name"],
                demand["demand"],
            ])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


tab_generate, tab_manage, tab_summary = st.tabs(
    ["📝 生成课程采购单", "🛠️ 采购单管理", "📊 汇总采购单"]
)

# ==================== 1. 生成课程采购单 ====================
with tab_generate:
    if not is_admin:
        st.warning("权限不足：生成采购单仅限管理员及以上角色使用。")
    else:
        _semester_result = semester_stats_service.list_semesters()
        semesters = _semester_result.data if _semester_result.is_success() else []

        if not semesters:
            st.info("暂无可用的用量学年数据（需要存在已关联课程/实验的「领用 → 归还」记录）。")
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                source_semester = st.selectbox("用量来源学年", options=semesters, key="cp_source_semester")
            course_names = purchase_service.list_course_names()
            with col2:
                course_name = st.selectbox("课程", options=[""] + course_names, key="cp_course_name")
            with col3:
                target_students = st.number_input(
                    "预计人数", min_value=1, max_value=500,
                    value=DEFAULT_TARGET_STUDENT_COUNT, step=1, key="cp_target_students"
                )
            with col4:
                target_semester = st.text_input(
                    "目标学年", value=_next_semester(source_semester), key="cp_target_semester",
                    help="采购单归属的学年，如 2026-2027"
                )

            if st.button("预览人均用量与需求", type="primary", use_container_width=True):
                if not course_name:
                    st.warning("⚠️ 请先选择课程")
                else:
                    result = purchase_service.preview_course_plan(
                        course_name, source_semester, int(target_students)
                    )
                    st.session_state["cp_preview"] = result.data if result.is_success() else None
                    st.session_state["cp_preview_msg"] = result.message

            preview = st.session_state.get("cp_preview")
            preview_msg = st.session_state.get("cp_preview_msg")
            if preview_msg:
                st.info(preview_msg)

            if preview and preview.get("course_name") == course_name:
                st.caption(
                    f"历史人数 {preview['source_student_count']} → 预计人数 "
                    f"{preview['target_student_count']}（课程：{preview['course_name']}）"
                )
                st.dataframe(
                    [
                        {
                            "实验": row["item_name"],
                            "试剂名称": row["reagent_name"],
                            "历史用量": row["source_quantity"],
                            "人均用量": row["per_capita_usage"],
                            "预计人数": row["student_count"],
                            "需求量": row["demand_quantity"],
                            "当前库存(参考)": row["current_stock"],
                        }
                        for row in preview["items"]
                    ],
                    use_container_width=True,
                    hide_index=True
                )

                if st.button("生成 / 覆盖采购单", type="primary", use_container_width=True):
                    if not target_semester.strip():
                        st.warning("⚠️ 请填写目标学年")
                    else:
                        result = purchase_service.generate_course_plan(
                            course_name=course_name,
                            source_semester=source_semester,
                            target_semester=target_semester.strip(),
                            target_student_count=int(target_students),
                            created_by=current_user,
                        )
                        if result.is_success():
                            st.success(f"✅ {result.message}")
                            st.session_state["cp_preview"] = None
                            st.rerun()
                        else:
                            st.error(f"❌ {result.message}")

# ==================== 2. 采购单管理 ====================
with tab_manage:
    if not is_admin:
        st.warning("权限不足：修改采购单仅限管理员及以上角色使用。")
    else:
        target_semesters = purchase_service.list_target_semesters()
        if not target_semesters:
            st.info("暂无采购单，请先在「生成课程采购单」中生成。")
        else:
            selected_semester = st.selectbox("目标学年", options=target_semesters, key="cp_manage_semester")
            plans = purchase_service.list_plans(selected_semester)

            if not plans:
                st.info("该学年暂无采购单")
            else:
                options = {
                    p.id: f"{p.plan_number}｜{p.course_name}｜{p.item_count} 条"
                    for p in plans
                }
                plan_id = st.selectbox(
                    "选择采购单",
                    options=list(options.keys()),
                    format_func=lambda pid: options.get(pid, str(pid)),
                    key="cp_manage_plan"
                )
                plan = next((p for p in plans if p.id == plan_id), None)
                if plan:
                    st.caption(
                        f"课程：{plan.course_name}｜来源学年 {plan.source_semester}｜"
                        f"历史人数 {plan.source_student_count} → 预计人数 {plan.target_student_count}"
                        f"｜状态 {plan.status}"
                    )

                    detail = purchase_service.get_plan_detail(plan_id)
                    edited = st.data_editor(
                        [
                            {
                                "id": row["id"],
                                "实验": row["item_name"],
                                "试剂名称": row["reagent_name"],
                                "人均用量": row["per_capita_usage"],
                                "需求量": row["demand_quantity"],
                                "采购量": row["purchase_quantity"],
                                "供应商": row["supplier"] or "",
                                "备注": row["remark"] or "",
                                "已改": bool(row["is_manual"]),
                            }
                            for row in detail
                        ],
                        column_config={
                            "id": None,
                            "实验": st.column_config.TextColumn(disabled=True),
                            "试剂名称": st.column_config.TextColumn(disabled=True),
                            "人均用量": st.column_config.NumberColumn(disabled=True, format="%.4f"),
                            "需求量": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                            "采购量": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                            "供应商": st.column_config.TextColumn(),
                            "备注": st.column_config.TextColumn(),
                            "已改": st.column_config.CheckboxColumn(disabled=True),
                        },
                        hide_index=True,
                        use_container_width=True,
                        num_rows="fixed",
                        key=f"cp_edit_{plan_id}"
                    )

                    if st.button("保存修改", type="primary", use_container_width=True):
                        updates = [
                            {
                                "id": row["id"],
                                "demand_quantity": row["需求量"],
                                "purchase_quantity": row["采购量"],
                                "supplier": row["供应商"] or None,
                                "remark": row["备注"] or None,
                            }
                            for row in edited
                        ]
                        result = purchase_service.update_plan_items(
                            plan_id, updates, updated_by=current_user
                        )
                        if result.is_success():
                            st.success(f"✅ {result.message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {result.message}")

# ==================== 3. 汇总采购单（超管）====================
with tab_summary:
    if not is_super_admin:
        st.warning("权限不足：汇总采购单仅限超级管理员使用。")
    else:
        target_semesters = purchase_service.list_target_semesters()
        if not target_semesters:
            st.info("暂无采购单可汇总。")
        else:
            col1, col2 = st.columns([2, 1])
            with col1:
                summary_semester = st.selectbox(
                    "目标学年", options=target_semesters, key="cp_summary_semester"
                )
            with col2:
                only_need = st.checkbox("只看需要采购", value=True, key="cp_only_need")

            result = purchase_service.summarize(summary_semester)
            rows = result.data if result.is_success() else []
            if not rows:
                st.info(result.message)
            else:
                st.success(result.message)
                display = [r for r in rows if r["need_purchase"]] if only_need else rows
                st.dataframe(
                    [
                        {
                            "试剂名称": r["reagent_name"],
                            "CAS号": r["cas_number"] or "-",
                            "总需求": r["total_demand"],
                            "当前库存": r["current_stock"],
                            "最终采购量": r["final_purchase"],
                            "需采购": "✅" if r["need_purchase"] else "—",
                            "供应商": r["supplier"] or "-",
                        }
                        for r in display
                    ],
                    use_container_width=True,
                    hide_index=True
                )
                st.caption(f"共 {len(display)} 种试剂")

                st.download_button(
                    label="📥 导出 Excel（采购汇总 + 课程需求明细）",
                    data=_build_summary_excel(display, summary_semester),
                    file_name=f"采购汇总_{summary_semester}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
                st.caption("🖨️ 打印：可导出后在 Excel 中排版打印，也可直接用浏览器打印本页（Ctrl / Cmd + P）")

                st.markdown("**各课程需求明细**")
                course_rows = []
                for row in display:
                    for demand in row["course_detail"]:
                        course_rows.append({
                            "试剂名称": row["reagent_name"],
                            "课程": demand["course_name"],
                            "实验": demand["item_name"],
                            "需求": demand["demand"],
                        })
                if course_rows:
                    st.dataframe(course_rows, use_container_width=True, hide_index=True)
