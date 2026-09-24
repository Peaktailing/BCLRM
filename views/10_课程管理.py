"""课程管理页面

导入学院实验分组表（CSV / Excel）并维护实验课程。

权限：
- 查看课程列表：所有登录用户
- 导入课程：管理员及以上（admin / super_admin）
- 删除课程：超级管理员
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from components.sidebar_nav import render_sidebar
from components.auth import require_auth
from business.course_import_service import course_import_service
from business.experiment_plan_service import experiment_plan_business
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service

st.set_page_config(page_title="课程管理", layout="wide")

if not require_auth():
    st.stop()

render_sidebar()

st.title("📚 课程管理")
st.caption("导入学院实验分组表（CSV / Excel）维护实验课程；不同学年或学院的分组表可分别导入。")

is_admin = bool(st.session_state.get("is_admin", False))
is_super_admin = st.session_state.get("user_role") == "super_admin"

tab_import, tab_add, tab_list = st.tabs(["📥 导入课程", "➕ 新增课程/实验", "📋 课程列表"])

# ---------- 导入课程（管理员及以上） ----------
with tab_import:
    if not is_admin:
        st.warning("权限不足：导入课程仅限管理员及以上角色使用。")
    else:
        uploaded = st.file_uploader(
            "选择实验分组表（CSV / Excel）",
            type=["csv", "xlsx", "xls"]
        )

        if uploaded is None:
            st.info("请选择实验分组表文件。表格前 3 行需为标题、表头、子表头（与学院导出模板一致）。")
        else:
            parsed = course_import_service.parse(uploaded, uploaded.name)
            if parsed.is_failure():
                st.error(f"❌ {parsed.message}")
            else:
                info = parsed.data
                courses = info["courses"]
                items = info.get("items") or []
                st.success(f"解析成功：{parsed.message}")

                col1, col2, col3 = st.columns(3)
                college = col1.text_input("学院", value=info.get("college") or "")
                semester = col2.text_input(
                    "学年", value=info.get("semester") or "", help="格式如 2026-2027"
                )
                term = col3.text_input("学期", value=info.get("term") or "", help="如 1")

                st.markdown("**课程预览**")
                st.dataframe(
                    [
                        {
                            "课程名称": c.get("course_name"),
                            "班级": c.get("class_name") or "-",
                            "教师": c.get("teacher") or "-",
                            "班级人数": c.get("student_count") or 0,
                            "地点": c.get("location") or "-",
                        }
                        for c in courses
                    ],
                    use_container_width=True,
                    hide_index=True
                )

                st.caption(
                    f"解析到 {len(items)} 个实验项目"
                    "（与已有项目按「课程名 + 实验名」跨学年去重）"
                )

                if st.button("确认导入", type="primary", use_container_width=True):
                    result = course_import_service.import_courses(
                        courses,
                        semester=semester.strip(),
                        term=term.strip(),
                        college=college.strip() or None,
                        items=items,
                    )
                    if result.is_success():
                        st.success(f"✅ 导入完成：{result.message}")
                    else:
                        st.error(f"❌ {result.message}")

# ---------- 新增课程 / 实验项目（超级管理员） ----------
with tab_add:
    if not is_super_admin:
        st.warning("权限不足：新增实验课程与实验项目仅限超级管理员使用。")
    else:
        # ========== 新增课程 ==========
        st.subheader("➕ 新增实验课程")
        st.caption("手动录入一条课程（学年 + 学期 + 课程名 + 班级 唯一）。")

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            _new_semester = st.text_input(
                "学年*", placeholder="2026-2027", key="add_course_semester"
            )
        with col_b:
            _new_term = st.text_input("学期*", placeholder="1", key="add_course_term")
        with col_c:
            _new_class = st.text_input(
                "班级", placeholder="2024级1班", key="add_course_class"
            )

        col_d, col_e = st.columns(2)
        with col_d:
            _new_course_name = st.text_input(
                "课程名称*", placeholder="食品微生物学实验", key="add_course_name"
            )
        with col_e:
            _new_teacher = st.text_input("任课教师", key="add_course_teacher")

        col_f, col_g, col_h = st.columns(3)
        with col_f:
            _new_major = st.text_input("开课专业", key="add_course_major")
        with col_g:
            _new_count = st.number_input(
                "班级人数", min_value=0, value=0, step=1, key="add_course_count"
            )
        with col_h:
            _new_location = st.text_input("上课地点", key="add_course_location")

        _new_college = st.text_input("开课学院", key="add_course_college")

        if st.button(
            "新增课程",
            type="primary",
            use_container_width=True,
            key="add_course_btn",
        ):
            if not _new_semester.strip() or not _new_term.strip() or not _new_course_name.strip():
                st.warning("⚠️ 学年、学期、课程名称为必填项")
            else:
                try:
                    _created_course = experiment_course_service.create({
                        "semester": _new_semester.strip(),
                        "term": _new_term.strip(),
                        "course_name": _new_course_name.strip(),
                        "class_name": _new_class.strip() or None,
                        "major": _new_major.strip() or None,
                        "teacher": _new_teacher.strip() or None,
                        "student_count": int(_new_count) or None,
                        "location": _new_location.strip() or None,
                        "college": _new_college.strip() or None,
                    })
                except Exception as exc:
                    _created_course = None
                    st.error(f"❌ 新增失败：{exc}")

                if _created_course:
                    for _key in ("add_course_name", "add_course_teacher"):
                        st.session_state.pop(_key, None)
                    st.success(f"✅ 已新增课程：{_new_course_name.strip()}")
                    st.rerun()
                elif _created_course is None:
                    st.error(
                        "❌ 新增失败（可能已存在相同的「学年 + 学期 + 课程名 + 班级」）"
                    )

        st.divider()

        # ========== 新增实验项目 ==========
        st.subheader("➕ 新增实验项目")
        st.caption("从已有课程中选择一门，为其添加实验项目（同一课程下实验名称不可重复）。")

        _all_courses = experiment_course_service.get_by_semester(None)
        _course_for_item = st.selectbox(
            "选择课程",
            options=[""] + sorted({
                c.course_name for c in _all_courses if c.course_name
            }),
            key="add_item_course",
        )

        if not _course_for_item:
            st.info("请先选择课程")
        else:
            _existing_items = experiment_item_service.get_by_course(_course_for_item)
            _next_seq = max([i.seq or 0 for i in _existing_items] or [0]) + 1

            col_i1, col_i2 = st.columns([3, 1])
            with col_i1:
                _new_item_name = st.text_input(
                    "实验名称*",
                    placeholder="实验三：xxx",
                    key="add_item_name",
                )
            with col_i2:
                _new_item_seq = st.number_input(
                    "序号",
                    min_value=1,
                    value=int(_next_seq),
                    step=1,
                    key="add_item_seq",
                )

            st.caption(
                f"该课程现有 {len(_existing_items)} 个实验项目"
                + (
                    "：" + "、".join(i.item_name for i in _existing_items[:5])
                    + ("…" if len(_existing_items) > 5 else "")
                    if _existing_items else ""
                )
            )

            if st.button(
                "新增实验项目",
                type="primary",
                use_container_width=True,
                key="add_item_btn",
            ):
                _item_name_clean = _new_item_name.strip()
                if not _item_name_clean:
                    st.warning("⚠️ 请填写实验名称")
                elif any(i.item_name == _item_name_clean for i in _existing_items):
                    st.warning("⚠️ 该课程下已存在同名实验项目")
                else:
                    _item_semester = next(
                        (
                            c.semester for c in _all_courses
                            if c.course_name == _course_for_item
                        ),
                        None,
                    )
                    try:
                        _created_item = experiment_item_service.create({
                            "semester": _item_semester,
                            "course_name": _course_for_item,
                            "seq": int(_new_item_seq),
                            "item_name": _item_name_clean,
                        })
                    except Exception as exc:
                        _created_item = None
                        st.error(f"❌ 新增失败：{exc}")

                    if _created_item:
                        st.session_state.pop("add_item_name", None)
                        st.success(f"✅ 已新增实验项目：{_item_name_clean}")
                        st.rerun()
                    elif _created_item is None:
                        st.error("❌ 新增失败（该课程下可能已存在同名实验项目）")

# ---------- 课程列表 ----------
with tab_list:
    semesters = experiment_course_service.list_semesters()
    selected = st.selectbox(
        "学年筛选", options=["全部"] + list(semesters), key="course_list_semester"
    )
    target = None if selected == "全部" else selected

    courses = experiment_course_service.get_by_semester(target)
    if not courses:
        st.info("暂无课程，请先在「导入课程」中导入实验分组表。")
    else:
        st.dataframe(
            [
                {
                    "学年": c.semester,
                    "学期": c.term,
                    "课程名称": c.course_name,
                    "班级": c.class_name or "-",
                    "教师": c.teacher or "-",
                    "班级人数": c.student_count or 0,
                    "地点": c.location or "-",
                }
                for c in courses
            ],
            use_container_width=True,
            hide_index=True
        )
        st.caption(f"共 {len(courses)} 条课程")

        # ---------- 课程下的实验项目 ----------
        st.divider()
        st.subheader("课程下的实验项目")
        _course_names = sorted({c.course_name for c in courses if c.course_name})
        selected_course_name = st.selectbox(
            "选择课程", options=[""] + _course_names, key="item_course_select"
        )
        if selected_course_name:
            course_items = experiment_item_service.get_by_course(selected_course_name)
            if not course_items:
                st.info("该课程暂无实验项目（重新导入分组表即可补充）")
            else:
                # 实验项目列表（含试剂领用进度）
                _status_map = experiment_plan_business.get_status_map(target)
                st.dataframe(
                    [
                        {
                            "序号": i.seq,
                            "实验名称": i.item_name,
                            "试剂领用进度": _status_map.get(
                                (i.course_name, i.item_name), "未领用"
                            ),
                        }
                        for i in course_items
                    ],
                    use_container_width=True,
                    hide_index=True
                )
                st.caption(f"共 {len(course_items)} 个实验项目")

                # ---------- 默认实验方案与默认用量 ----------
                st.markdown("#### 🧪 默认实验方案与用量")
                st.caption(
                    "默认用量按「人均用量」维护，领用时按班级人数折算为本次总量。"
                )
                if not is_admin:
                    st.caption("🔒 只读视图：维护默认方案与用量需「管理员」及以上权限。")
                _item_names = [i.item_name for i in course_items]
                selected_item_name = st.selectbox(
                    "选择实验", options=[""] + _item_names, key="plan_item_select"
                )

                if selected_item_name:
                    _default_count = max(
                        [
                            c.student_count or 0
                            for c in courses
                            if c.course_name == selected_course_name
                        ]
                        or [0]
                    )

                    _plan_result = experiment_plan_business.get_plan(
                        selected_course_name, selected_item_name
                    )
                    _plan_data = (
                        _plan_result.data
                        if _plan_result.is_success()
                        else {"plan_text": None, "usages": []}
                    )

                    col_import, col_count = st.columns([2, 1])
                    with col_count:
                        _import_count = st.number_input(
                            "折算人数",
                            min_value=1,
                            value=_default_count or 1,
                            step=1,
                            key="plan_import_count",
                            help="按历史工单导入时，用该人数把整班量折算为人均用量",
                        )
                    with col_import:
                        st.write("")
                        if st.button(
                            "📥 按最近一次工单导入默认用量",
                            key="plan_import_btn",
                            use_container_width=True,
                            disabled=not is_admin,
                        ):
                            _r = experiment_plan_business.import_usage_from_history(
                                selected_course_name,
                                selected_item_name,
                                student_count=_import_count,
                            )
                            if _r.is_success():
                                st.success(f"✅ {_r.message}")
                                st.rerun()
                            else:
                                st.error(f"❌ {_r.message}")

                    _plan_text = st.text_area(
                        "实验方案",
                        value=_plan_data.get("plan_text") or "",
                        height=120,
                        key=f"plan_text_{selected_course_name}_{selected_item_name}",
                        placeholder="填写实验目的、步骤、注意事项等",
                    )

                    st.markdown("**默认用量（人均用量）**")
                    _usage_rows = [
                        {
                            "试剂名称": u["reagent_name"],
                            "人均用量": u["qty_per_person"],
                            "单位": u["unit"] or "g",
                            "来源": u["source"] or "手动",
                            "上次整班量": u["base_qty"],
                            "上次人数": u["base_student_count"],
                            "删除": "🗑️",
                        }
                        for u in _plan_data.get("usages", [])
                    ]
                    _edited_usages = st.data_editor(
                        _usage_rows,
                        column_config={
                            "单位": st.column_config.TextColumn(width="small"),
                            "来源": st.column_config.TextColumn(disabled=True, width="small"),
                            "上次整班量": st.column_config.NumberColumn(disabled=True),
                            "上次人数": st.column_config.NumberColumn(disabled=True),
                            "删除": st.column_config.TextColumn("操作", width="small"),
                        },
                        num_rows="dynamic",
                        use_container_width=True,
                        hide_index=True,
                        key=f"plan_usage_table_{selected_course_name}_{selected_item_name}",
                    )

                    _preview_count = st.number_input(
                        "按人数预览本次领用总量",
                        min_value=1,
                        value=_default_count or 1,
                        step=1,
                        key="plan_preview_count",
                    )

                    if st.button(
                        "💾 保存实验方案与默认用量",
                        type="primary",
                        use_container_width=True,
                        key="plan_save_btn",
                        disabled=not is_admin,
                    ):
                        _keep = [
                            row for row in _edited_usages
                            if row["删除"] == "🗑️" and row["试剂名称"]
                        ]
                        _save_result = experiment_plan_business.save_plan(
                            selected_course_name,
                            selected_item_name,
                            plan_text=_plan_text,
                            usages=[
                                {
                                    "reagent_name": row["试剂名称"],
                                    "qty_per_person": row["人均用量"],
                                    "unit": row["单位"],
                                    "base_qty": row["上次整班量"],
                                    "base_student_count": row["上次人数"],
                                    "source": row["来源"] or "手动",
                                }
                                for row in _keep
                            ],
                            replace_usages=True,
                        )
                        if _save_result.is_success():
                            st.success(f"✅ {_save_result.message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {_save_result.message}")

                    _preview_rows = [
                        {
                            "试剂名称": row["试剂名称"],
                            "人均用量": row["人均用量"],
                            "本次总量": round(
                                float(row["人均用量"] or 0) * _preview_count, 4
                            ),
                            "单位": row["单位"],
                        }
                        for row in _edited_usages
                        if row["试剂名称"]
                    ]
                    if _preview_rows:
                        st.caption(f"按 {_preview_count} 人折算的本次领用总量预览")
                        st.dataframe(
                            _preview_rows, use_container_width=True, hide_index=True
                        )

        # ---------- 删除实验项目（超级管理员；课程保留） ----------
        if is_super_admin:
            st.divider()
            st.subheader("🗑️ 删除实验项目（不影响课程）")
            st.caption(
                "只删除所选实验项目，**课程本身与其他实验项目保留**；"
                "历史领用记录使用名称快照，不受影响。"
            )
            _del_course = st.selectbox(
                "选择课程",
                options=[""] + list(_course_names),
                key="del_item_course_select",
            )
            if not _del_course:
                st.info("请先选择课程")
            else:
                _del_items = experiment_item_service.get_by_course(_del_course)
                if not _del_items:
                    st.info("该课程下暂无可删除的实验项目")
                else:
                    _del_options = {
                        item.id: f"{item.seq or '-'} | {item.item_name}"
                        for item in _del_items
                    }
                    with st.form("delete_item_form"):
                        _del_item_id = st.selectbox(
                            "选择实验项目",
                            options=list(_del_options.keys()),
                            format_func=lambda iid: _del_options.get(iid, str(iid)),
                            key="del_item_select",
                        )
                        _item_confirmed = st.checkbox(
                            "我确认删除该实验项目（课程保留）", key="del_item_confirm"
                        )
                        if st.form_submit_button(
                            "删除实验项目", type="primary", use_container_width=True
                        ):
                            if not _item_confirmed:
                                st.warning("⚠️ 请先勾选确认")
                            elif experiment_item_service.delete(_del_item_id):
                                st.success("✅ 实验项目已删除（课程保留）")
                                st.rerun()
                            else:
                                st.error("❌ 删除失败，请重试")

        # ---------- 删除课程（超级管理员） ----------
        if is_super_admin:
            st.divider()
            st.subheader("🗑️ 删除课程")
            st.caption("删除后该课程从列表移除；历史领用记录不受影响，但课程统计中不再显示。")

            options = {
                c.id: f"{c.semester}-{c.term} | {c.course_name}（{c.class_name or '-'}）"
                for c in courses
            }
            with st.form("delete_course_form"):
                target_id = st.selectbox(
                    "选择课程",
                    options=list(options.keys()),
                    format_func=lambda cid: options.get(cid, str(cid)),
                    key="del_course_select"
                )
                confirmed = st.checkbox("我确认删除该课程", key="del_course_confirm")
                if st.form_submit_button("删除课程", type="primary", use_container_width=True):
                    if not confirmed:
                        st.warning("⚠️ 请先勾选确认")
                    elif experiment_course_service.delete(target_id):
                        st.success("✅ 课程已删除")
                        st.rerun()
                    else:
                        st.error("❌ 删除失败，请重试")
