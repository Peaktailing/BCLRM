"""统一待办队列。

在这之前，管理员的待办散在两个页面：零星/课程领用工单在「领用归还」的
审批标签页，整门课的批量领料在「配方与需求」的领用单据里。两条路都走
「申请 → 审批 → 借出」，但数据结构不同，要跑两个地方才看得全。

本页只做一件事：**把两张表在办的单排成一队**，按提交时间升序。归属按
三级降级显形——我名下 / 本教研室池 / 全院池。接单、退回、转交都在这里，
判定全在服务层，页面只负责显示和发指令。

不在这里做的事：抽卡（管理员接单后到对应页面过目）、审批管控试剂（那
是另一条审批链，别混进队列的操作按钮里）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from business.assignment_service import (
    KIND_LABELS,
    KIND_ORDER,
    KIND_REQUIREMENT,
    assignment_service,
)
from components.auth import require_auth
from components.sidebar_nav import render_sidebar
from domain.assignment import Assignment

st.set_page_config(page_title="待办队列", layout="wide")

if not require_auth():
    st.stop()

render_sidebar()

st.title("📋 待办队列")
st.caption(
    "所有还在办的单在这里排成一队：零星/课程领用工单 + 配方需求单。"
    "归属三级降级——指定给我 → 本教研室谁接都行 → 全院谁接都行。"
)

user_name = st.session_state.get("user_name") or ""
is_admin = assignment_service.is_admin(user_name)
is_super = assignment_service.is_super_admin(user_name)
my_department = assignment_service.department_of(user_name)

# 操作结果在 rerun 之后才显示，所以先存进 session_state，渲染时取一次就清。
if "_queue_flash" in st.session_state:
    _level, _text = st.session_state.pop("_queue_flash")
    getattr(st, _level)(_text)


def _flash(result) -> None:
    st.session_state["_queue_flash"] = (
        "success" if result.is_success() else "warning",
        result.message,
    )


if not is_admin:
    st.info(
        "待办队列是管理员的受理台。教师不接单——您的申请进度在"
        "「配方与需求 → 领用单据」和「领用归还」里查看。"
    )
    st.stop()

# ---------------------------------------------------------------------------
# 取队列
# ---------------------------------------------------------------------------
rows = assignment_service.queue(user_name, my_department)
summary = assignment_service.queue_summary(user_name, my_department)

kpi_mine, kpi_dept, kpi_pool, kpi_all = st.columns(4)
kpi_mine.metric("我名下", summary["mine"])
kpi_dept.metric("本教研室池", summary["department"])
kpi_pool.metric("全院池", summary["pool"])
kpi_all.metric("合计", summary["total"])

with st.expander("筛选", expanded=False):
    filter_kind = st.radio(
        "单类型",
        options=["全部", KIND_LABELS[KIND_ORDER], KIND_LABELS[KIND_REQUIREMENT]],
        horizontal=True,
    )
    only_mine = st.checkbox("只看我名下", value=False)

if filter_kind != "全部":
    wanted = KIND_ORDER if filter_kind == KIND_LABELS[KIND_ORDER] else KIND_REQUIREMENT
    rows = [row for row in rows if row.get("kind") == wanted]
if only_mine:
    rows = [
        row
        for row in rows
        if (row.get("custodian_scope") or "") == "person"
        and (row.get("custodian_key") or "") == user_name
    ]

if not rows:
    if is_super and not only_mine:
        st.success("当前没有任何在办的单。")
    else:
        st.info("没有需要您处理的单。指定给别人的单不会出现在这里。")
    st.stop()

STATUS_LABELS = {
    "待审批": "待审批",
    "draft": "草稿",
    "submitted": "已提交",
    "partial": "部分兑付",
    "issued": "已兑付",
    "closed": "已关闭",
}


def _row_view(row: dict) -> dict:
    current = Assignment.of(
        row.get("custodian_scope") or "", row.get("custodian_key") or ""
    )
    return {
        "类型": KIND_LABELS.get(row.get("kind"), row.get("kind")),
        "单号": row.get("ref"),
        "内容": row.get("title") or "",
        "申请人": row.get("applicant") or "",
        "科室": row.get("department") or "（未登记）",
        "项数": int(row.get("item_count") or 0),
        "状态": STATUS_LABELS.get(row.get("status") or "", row.get("status") or ""),
        "归属": current.describe(),
        "提交时间": (row.get("created_at") or "")[:19],
    }


st.dataframe(
    pd.DataFrame([_row_view(row) for row in rows]),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("处理")

options = {f"{row.get('kind')}|{row.get('ref')}": row for row in rows}
choice = st.selectbox(
    "选择一张单",
    options=list(options.keys()),
    format_func=lambda key: (
        f"[{KIND_LABELS.get(options[key].get('kind'), '')}] "
        f"{options[key].get('ref')} · {options[key].get('title') or ''} · "
        f"{Assignment.of(options[key].get('custodian_scope') or '', options[key].get('custodian_key') or '').describe()}"
    ),
)
row = options[choice]
kind = row.get("kind")
ref = row.get("ref")
current = Assignment.of(row.get("custodian_scope") or "", row.get("custodian_key") or "")

st.markdown(
    f"**{KIND_LABELS.get(kind, kind)} {ref}** ｜ 申请人 {row.get('applicant') or '—'} ｜ "
    f"{current.describe()}"
)

col_claim, col_release, col_transfer = st.columns([1, 1, 2])

if current.can_claim(user_name, my_department, is_super_admin=is_super):
    if col_claim.button("接单", type="primary", use_container_width=True):
        _flash(assignment_service.claim(kind, ref, user_name, my_department))
        st.rerun()

if current.can_release(user_name, is_super_admin=is_super):
    hint = "接单人本人或超管才能退回" if not is_super else "超管代退"
    if col_release.button("退回池", help=hint, use_container_width=True):
        _flash(assignment_service.release(kind, ref, user_name, my_department))
        st.rerun()

if current.can_transfer(user_name, is_super_admin=is_super):
    candidates = [n for n in assignment_service.admin_names() if n != current.key]
    if candidates:
        target = col_transfer.selectbox("转交给", options=candidates, key=f"transfer_{kind}_{ref}")
        if col_transfer.button("转交", use_container_width=True):
            _flash(assignment_service.transfer(kind, ref, target, user_name))
            st.rerun()

if not (
    current.can_claim(user_name, my_department, is_super_admin=is_super)
    or current.can_release(user_name, is_super_admin=is_super)
):
    st.caption("这张单已指定他人受理；如确需改派，请联系超级管理员。")
