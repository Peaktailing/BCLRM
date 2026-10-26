"""统一待办队列。

在这之前，管理员的待办散在两个页面：零星/课程领用工单在「领用归还」的
审批标签页，整门课的批量领料在「配方与需求」的领用单据里。两条路都走
「申请 → 审批 → 借出」，但数据结构不同，要跑两个地方才看得全。

本页只做一件事：**把两张表在办的单排成一队**，按提交时间升序。归属按
三级降级显形——我名下 / 我的组 / 全院池。接单、退回、改派都在这里，判定
全在服务层，页面只负责显示和发指令。

关于「组」：一个人可能同时属于教研室和科研组，两个组池的单都会出现在这里。
组名后面的标签（教研室 / 科研组）只是让人看懂来源，不参与权限——权限只认
「我在不在这个组」。

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
from business.transfer_service import transfer_service
from components.auth import require_auth
from components.sidebar_nav import render_sidebar
from domain.assignment import Assignment
from services.base.work_group_service import GROUP_KIND_LABELS

st.set_page_config(page_title="待办队列", layout="wide")

if not require_auth():
    st.stop()

render_sidebar()

st.title("📋 待办队列")
st.caption(
    "所有还在办的单在这里排成一队：零星/课程领用工单 + 配方需求单。"
    "归属三级：指定给某人（只有他看得见）→ 我的组（组里任一管理员可接可办）"
    "→ 全院池（全院管理员可接可办）。"
)
st.caption(
    "三个动作别混：**退回修改 = 单有问题**（退给申请人改，单离开在办）；"
    "**改派 = 换人/换组办**（单还在办）；**手上没料 = 走调配**（单留在我名下）。"
)

user_name = st.session_state.get("user_name") or ""
is_admin = assignment_service.is_admin(user_name)
is_super = assignment_service.is_super_admin(user_name)
my_groups = assignment_service.groups_of(user_name)

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
        "「配方与需求 → 领用单据」和「领用归还」里查看；指定的人一直不批时，"
        "可以在「配方与需求 → 我的在办需求单」里把单放给组或全院。"
    )
    st.stop()

# ---------------------------------------------------------------------------
# 取队列
# ---------------------------------------------------------------------------
rows = assignment_service.queue(user_name, my_groups)
summary = assignment_service.queue_summary(user_name, my_groups)

kpi_mine, kpi_dept, kpi_pool, kpi_all = st.columns(4)
kpi_mine.metric("我名下", summary["mine"])
kpi_dept.metric("我的组", summary["department"])
kpi_pool.metric("全院池", summary["pool"])
kpi_all.metric("合计", summary["total"])

if my_groups:
    st.caption(
        "我所属的组："
        + "、".join(assignment_service.group_label(g) for g in my_groups)
    )
else:
    st.caption("⚠️ 你还没有登记所属的组，只能看到指定给你和全院池的单。")

# 调配单不进这个队列（队列是「谁该发料」，调拨是「谁该点头」），
# 但完全看不见也不行——出料人不点头，缺料的人就一直等。
_pending_transfers = transfer_service.pending_for(user_name)
_pending_count = len(_pending_transfers.data or [])
if _pending_count:
    st.info(
        f"另有 {_pending_count} 张调拨单等你点头（别人要从你名下调料）。"
        "这类单不进上面的队列——去「🔀 调配台」处理。"
    )

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
    "待复核": "待复核（双人审批）",
    "draft": "草稿",
    "submitted": "已提交",
    "partial": "部分兑付",
    "issued": "已兑付",
    "returned": "已退回修改",
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
        "申请人科室": row.get("department") or "（未登记）",
        "项数": int(row.get("item_count") or 0),
        "状态": STATUS_LABELS.get(row.get("status") or "", row.get("status") or ""),
        "归属": current.describe(),
        "组类型": GROUP_KIND_LABELS.get(row.get("custodian_group_kind") or "", ""),
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
applicant = row.get("applicant") or ""
# 能不能办（审批/发料）与能不能接是两件事：组池里的单两件都能做，谁办谁的
# 签名进流水。这里只做提示，真正的拦截在服务端。
_can_do, _why_not = assignment_service.can_handle(kind, ref, user_name)

_group_kind = GROUP_KIND_LABELS.get(row.get("custodian_group_kind") or "", "")
st.markdown(
    f"**{KIND_LABELS.get(kind, kind)} {ref}** ｜ 申请人 {applicant or '—'}"
    f"（{row.get('department') or '未登记科室'}） ｜ "
    f"{current.describe()}"
    + (f" · {_group_kind}" if _group_kind else "")
    + " ｜ "
    + ("✅ 你可以受理这张单" if _can_do else f"⛔ {_why_not}")
)

col_claim, col_return = st.columns([1, 1])

_can_claim = current.can_claim(user_name, my_groups, is_super_admin=is_super)
_can_return = current.can_return(
    user_name, my_groups, is_admin=is_admin, is_super_admin=is_super
)
_can_transfer = current.can_transfer(
    user_name, applicant, is_super_admin=is_super
)

if _can_claim:
    if col_claim.button("接单", type="primary", use_container_width=True):
        _flash(assignment_service.claim(kind, ref, user_name, my_groups))
        st.rerun()

if _can_return:
    # 退回 = 退单要申请人改，不是把活推给别人。原因可以不填：退这个动作本身
    # 已经说明「不能按现在这样批」，细节线下说清即可。
    _return_reason = st.text_input(
        "退回说明（可选）",
        placeholder="例：第 3 行数量按人数算多了；这瓶是管制试剂，须先走审批",
        key=f"return_reason_{kind}_{ref}",
    )
    if col_return.button(
        "退回修改",
        help="单有问题才退：数量、瓶子、用途、课程挂错。手上没料请走调配，单不动",
        use_container_width=True,
    ):
        _flash(
            assignment_service.return_for_revision(
                kind, ref, user_name, _return_reason, my_groups
            )
        )
        st.rerun()

if _can_transfer:
    _targets = assignment_service.transfer_options()
    if _targets:
        _values = [value for value, _label in _targets]
        _labels = dict(_targets)
        _pick = st.selectbox(
            "改派给（人 / 组）",
            options=_values,
            format_func=lambda v: _labels.get(v, v),
            key=f"transfer_{kind}_{ref}",
        )
        if st.button(
            "改派",
            help="换一个人或换一个组办。单还在办，状态不变",
            use_container_width=False,
        ):
            _flash(assignment_service.transfer(kind, ref, _pick, user_name))
            st.rerun()

if not (_can_claim or _can_return or _can_transfer):
    st.caption(
        f"{current.describe()}；这张单不归你办。需要改派请联系超级管理员。"
    )
