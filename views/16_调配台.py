"""调配台：管理员之间的横向通道。

第一段兑付时手上不够，过去只有两条出路：少发（需求单停在「部分兑付」）
或者等采购。院里别处有料却没有通道——这个页面就是那条通道。

四步在这里各有落点：

| 区域 | 谁用 | 做什么 |
|---|---|---|
| 我的缺口 | 缺料的管理员 | 看「我名下还没发出去的量」，点「算一算该找谁调」 |
| 待我点头 | 出料的管理员 | 逐行勾选同意 / 不同意（必写理由） |
| 我发起的 | 发起人 | 看进度、撤回还没被点头的单、标记实物已取走 |
| 全院在办 | 所有人 | 看这一轮横向流动有多忙（纯读） |

**调的是保管权，不是实物。** 点完头，瓶子还在原处，变的是「算谁名下」；
实物什么时候搬是线下的事，用「标记已取走」记一笔，不阻断流程。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from business.assignment_service import assignment_service
from business.transfer_service import transfer_service
from components.auth import require_auth
from components.sidebar_nav import render_sidebar
from domain.transfer import ITEM_PENDING, TRANSFER_REQUESTED

st.set_page_config(page_title="调配台", layout="wide")

if not require_auth():
    st.stop()

render_sidebar()

st.title("🔀 调配台")
st.caption(
    "管理员之间的横向通道：**缺口 → 建议 → 对方点头 → 平账**。"
    "调的是**保管权**，瓶子不动、库存总量不变；"
    "变更会写进管理人变更记录，可追溯。"
)
st.caption(
    "与另外两条路的分界：**借还**不动保管权；**采购**增加总量；"
    "**调配**只换「算谁名下」。手上没料不是退单理由——退单是「单本身有问题」。"
)

user_name = st.session_state.get("user_name") or ""
is_admin = assignment_service.is_admin(user_name)
is_super = assignment_service.is_super_admin(user_name)

if "_transfer_flash" in st.session_state:
    _level, _text = st.session_state.pop("_transfer_flash")
    getattr(st, _level)(_text)


def _flash(result) -> None:
    st.session_state["_transfer_flash"] = (
        "success" if result.is_success() else "warning",
        result.message,
    )


if not is_admin:
    st.info(
        "调配台是管理员之间的账。教师的申请进度在「配方与需求 → 领用单据」里看；"
        "料不够时由受理的管理员发起调配，您不需要来这里。"
    )
    st.stop()

summary = transfer_service.summary(user_name)
_kpi = summary.data if summary.success else {}
col1, col2, col3, col4 = st.columns(4)
col1.metric("待我点头", _kpi.get("pending_for_me", 0))
col2.metric("别人欠我的", _kpi.get("waiting_for_others", 0))
col3.metric("我的缺口", _kpi.get("my_gaps", 0))
col4.metric("全院在办", _kpi.get("open_all", 0))

tab_pending, tab_gaps, tab_mine, tab_all = st.tabs(
    ["待我点头", "我的缺口（发起调配）", "我发起的", "全院在办"]
)

# ---------------------------------------------------------------------------
# 待我点头
# ---------------------------------------------------------------------------
with tab_pending:
    st.markdown("##### 别人名下缺料，想从你这儿调——只有你本人能点头")
    st.caption(
        "逐行勾选：3 瓶里给 2 瓶是常态。不同意要写一句理由——"
        "对方得知道是「没有」还是「不给」，他好改去找别人或走采购。"
    )
    pending = transfer_service.pending_for(user_name)
    orders = pending.data or []
    if not orders:
        st.info("没有等你点头的单。指定给别人的单不会出现在这里。")

    for order in orders:
        head = (
            f"{order.transfer_number} · {order.to_manager} 想调 "
            f"{len(order.items)} 瓶 · 来源 {order.origin_ref or '手工'}"
        )
        with st.expander(head, expanded=True):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "瓶号": item.lot_id or "现场指定",
                            "物质": item.display_name or item.substance_key,
                            "数量": f"{item.quantity:g} {item.unit or ''}",
                            "说明": item.note or "",
                        }
                        for item in order.items
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
            labels = [
                f"{index}｜{item.lot_id or '现场指定'} · {item.display_name or ''} "
                f"{item.quantity:g}{item.unit or ''}"
                for index, item in enumerate(order.items)
            ]
            chosen = st.multiselect(
                "同意哪几行（不选的行视为不同意）",
                options=list(range(len(order.items))),
                default=[
                    index
                    for index, item in enumerate(order.items)
                    if (item.line_status or "") == ITEM_PENDING
                ],
                format_func=lambda index: labels[index],
                key=f"pick_{order.id}",
            )
            remark = st.text_input(
                "备注（代签时必填）",
                key=f"remark_{order.id}",
                placeholder="同意可以留空；超管代签必须写清为什么代签",
            )
            as_super = is_super and user_name != (order.from_manager or "")
            btn_col1, btn_col2 = st.columns([1, 1])
            if btn_col1.button(
                "代签并转保管权" if as_super else "同意所选（即生效）",
                key=f"accept_{order.id}",
                type="primary",
            ):
                if as_super and not remark.strip():
                    st.warning("代签必须写理由：出料人为什么不能自己点头。")
                else:
                    _flash(
                        transfer_service.accept(
                            order.id,
                            user_name,
                            selections=chosen,
                            remark=remark,
                            is_super_admin=is_super,
                        )
                    )
                    st.rerun()
            with btn_col2:
                if st.button("全部不同意", key=f"reject_{order.id}"):
                    _flash(transfer_service.reject(order.id, user_name, remark))
                    st.rerun()

# ---------------------------------------------------------------------------
# 我的缺口
# ---------------------------------------------------------------------------
with tab_gaps:
    st.markdown("##### 我名下还没发出去的量")
    st.caption(
        "只列**认领到我名下**的单：组池与全院池的单还没有主人，缺口也就没有主人"
        "——谁先认领谁负责调。受理之后可以在这里看「该找谁调」，也可以先不调，"
        "等对方把料还回来。"
    )
    gaps = transfer_service.my_gaps(user_name)
    if not gaps.success:
        st.error(gaps.message)
    elif not gaps.data:
        st.info("你名下没有缺口。全部兑付完了，或者还没有受理的单。")
    for gap in gaps.data or []:
        with st.expander(
            f"{gap['sheet_number']} · {gap['title'] or ''} · "
            f"{len(gap['lines'])} 项缺口（合计 {gap['shortfall']:g}）",
            expanded=False,
        ):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "物质": line["name"],
                            "需求": f"{line['need']:g} {line['unit']}",
                            "已发": f"{line['issued']:g} {line['unit']}",
                            "缺口": f"{line['remaining']:g} {line['unit']}",
                        }
                        for line in gap["lines"]
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
            key = f"proposal_{gap['sheet_number']}"
            if st.button("算一算该找谁调", key=f"propose_{gap['sheet_number']}"):
                proposed = transfer_service.propose(gap["sheet_number"], user_name)
                if proposed.success:
                    st.session_state[key] = proposed.data
                else:
                    st.session_state.pop(key, None)
                    st.warning(proposed.message)

            proposal = st.session_state.get(key)
            if proposal is None:
                continue
            if not proposal["groups"]:
                st.warning("其他管理员名下也没有可调的量，这单得走采购或等采购到货。")
            for group in proposal["groups"]:
                span = "跨科室" if group["cross_department"] else "同科室"
                st.markdown(
                    f"**{group['supplier']}**"
                    f"（{group['department'] or '未登记科室'} · {span}）"
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "瓶号": line["lot_id"] or "现场指定",
                                "物质": line["name"],
                                "数量": f"{line['quantity']:g} {line['unit']}",
                                "说明": line["note"],
                            }
                            for line in group["lines"]
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                if st.button(
                    f"发给 {group['supplier']} 点头", key=f"req_{gap['sheet_number']}_{group['supplier']}"
                ):
                    _flash(
                        transfer_service.request(
                            gap["sheet_number"], group["supplier"], user_name
                        )
                    )
                    st.rerun()
            if proposal["unresolved"]:
                st.warning(
                    "调不到的缺口（需采购）："
                    + "；".join(
                        f"{item['name']} {item['quantity']:g}{item['unit']}"
                        for item in proposal["unresolved"]
                    )
                )
                purchase = proposal.get("purchase_sheet")
                if purchase is not None:
                    st.caption(
                        "这部分可以转成采购需求单：在「配方与需求 → 采购」里按缺口补。"
                    )

# ---------------------------------------------------------------------------
# 我发起的
# ---------------------------------------------------------------------------
with tab_mine:
    st.markdown("##### 我发起过的调拨")
    mine = transfer_service.mine(user_name, include_closed=True)
    orders = mine.data or []
    if not orders:
        st.info("还没有发起过调拨。缺口在左边那个标签页里发起。")
    if orders:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "单号": order.transfer_number,
                        "从谁": order.from_manager,
                        "到谁": order.to_manager,
                        "状态": order.status,
                        "瓶数": len(order.items),
                        "来源": order.origin_ref or "手工",
                        "发起": (order.requested_at or "")[:19],
                        "回复": order.answer_remark or "",
                        "代签": "是" if order.forced else "",
                        "已取走": (order.picked_up_at or "")[:19],
                    }
                    for order in orders
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    open_ones = [order for order in orders if (order.status or "") == TRANSFER_REQUESTED]
    for order in open_ones:
        if st.button(f"撤回 {order.transfer_number}", key=f"cancel_{order.id}"):
            _flash(transfer_service.cancel(order.id, user_name))
            st.rerun()

    accepted = [order for order in orders if (order.status or "") == "已同意"]
    for order in accepted:
        if not order.picked_up_at:
            if st.button(
                f"标记实物已取走（{order.transfer_number}）", key=f"pick_{order.id}"
            ):
                _flash(transfer_service.mark_picked_up(order.id))
                st.rerun()

# ---------------------------------------------------------------------------
# 全院在办
# ---------------------------------------------------------------------------
with tab_all:
    st.markdown("##### 全院在办（待点头）")
    st.caption(
        "调配单**不进统一待办队列**：队列是「谁该发料」，调拨是「谁该点头」。"
        "混在一起，队列就不再是一眼能扫完的东西了。"
    )
    every = transfer_service.open_all()
    orders = every.data or []
    if not orders:
        st.info("全院没有在办的调拨。")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "单号": order.transfer_number,
                        "出料人": order.from_manager,
                        "受益人": order.to_manager,
                        "状态": order.status,
                        "瓶数": len(order.items),
                        "来源": order.origin_ref or "手工",
                        "发起人": order.requested_by,
                    }
                    for order in orders
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
