"""学期用量统计页面

用量口径：领用量 − 还入量（在每次归还时计算并写入记录），
按学期聚合出总用量、领用人数与人均用量。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from components.sidebar_nav import render_sidebar
from components.auth import require_auth
from business.semester_stats_service import semester_stats_service

st.set_page_config(page_title="学期用量", layout="wide")

if not require_auth():
    st.stop()

render_sidebar()

st.title("📈 学期用量统计")
st.caption("用量口径：领用量 − 还入量（在每次归还时计算并记录）")

# ---------- 学期选择 ----------
_semester_result = semester_stats_service.list_semesters()
semesters = _semester_result.data if _semester_result.is_success() else []

selected = st.selectbox(
    "选择学期",
    options=["全部"] + semesters,
    key="semester_select"
)
semester = None if selected == "全部" else selected

# ---------- 汇总指标 ----------
_summary_result = semester_stats_service.get_usage_summary(semester)
summary = _summary_result.data if _summary_result.is_success() else {}

col1, col2, col3, col4 = st.columns(4)
col1.metric("总用量", f"{summary.get('total_usage', 0):,.2f}")
col2.metric("领用人数", summary.get("user_count", 0))
col3.metric("试剂种类", summary.get("reagent_count", 0))
col4.metric(
    "领用 / 归还次数",
    f"{summary.get('borrow_count', 0)} / {summary.get('return_count', 0)}"
)
st.caption(
    "人均用量按「每种试剂各自计算」（见下方按试剂用量），"
    "不做全部试剂加总后的笼统平均。"
)

st.divider()

# ---------- 按「课程 - 实验 - 试剂」用量（含人均） ----------
st.subheader("按「课程 → 实验 → 试剂」用量（含人均）")
st.caption(
    "同一课程下「实验名称 + 试剂名称」相同即合并为一行（**不分班级**）："
    "平均用量 = 合计用量 ÷ 班级数；人均用量 = 平均用量 ÷ 班级平均人数"
)
_detail_result = semester_stats_service.get_usage_by_course_item_reagent(semester)
detail_rows = _detail_result.data if _detail_result.is_success() else []

if detail_rows:
    st.caption(_detail_result.message)

    _course_options = ["全部"] + sorted({row["课程"] for row in detail_rows})
    _selected_course = st.selectbox(
        "课程筛选", options=_course_options, key="usage_detail_course"
    )
    _view_rows = (
        detail_rows if _selected_course == "全部"
        else [row for row in detail_rows if row["课程"] == _selected_course]
    )

    st.dataframe(_view_rows, use_container_width=True, hide_index=True)

    _df_detail = pd.DataFrame(_view_rows).head(15).copy()
    _df_detail["实验 · 试剂"] = _df_detail["实验"] + " · " + _df_detail["试剂"]
    st.bar_chart(
        _df_detail[["实验 · 试剂", "平均用量"]],
        x="实验 · 试剂", y="平均用量", color="#9C27B0", use_container_width=True
    )
else:
    st.info("暂无用量数据（需领用时关联课程与实验，且存在用量）")

# ---------- 按领用人用量 ----------
st.subheader("按领用人用量")
_user_result = semester_stats_service.get_usage_by_user(semester)
user_rows = _user_result.data if _user_result.is_success() else []

if user_rows:
    st.dataframe(user_rows, use_container_width=True, hide_index=True)
    df_user = pd.DataFrame(user_rows)[["领用人", "用量"]]
    st.bar_chart(df_user, x="领用人", y="用量", color="#4CAF50", use_container_width=True)
else:
    st.info("暂无用量数据（需要存在「领用 → 归还」记录）")

# ---------- 按课程用量（含人均） ----------
st.divider()
st.subheader("按实验课程用量（含人均）")
_course_result = semester_stats_service.get_usage_by_course(semester)
course_rows = _course_result.data if _course_result.is_success() else []

if course_rows:
    st.dataframe(course_rows, use_container_width=True, hide_index=True)
    df_course = pd.DataFrame(course_rows)[["课程", "用量"]]
    st.bar_chart(df_course, x="课程", y="用量", color="#FF9800", use_container_width=True)
else:
    st.info("暂无课程用量数据（需领用时关联实验课程，且完成归还）")

# ---------- 按月用量趋势 ----------
st.divider()
st.subheader("按月份用量趋势")
_month_result = semester_stats_service.get_usage_by_month(semester)
month_data = _month_result.data if _month_result.is_success() else {}

if month_data:
    df_month = pd.DataFrame(
        [{"月份": month, "用量": value} for month, value in month_data.items()]
    )
    st.bar_chart(df_month, x="月份", y="用量", color="#2196F3", use_container_width=True)
else:
    st.info("暂无按月用量数据")
