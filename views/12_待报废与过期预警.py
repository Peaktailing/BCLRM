"""待报废与过期预警页面

- 待报废清单：归还时「归还比例 0%」判定的空瓶会自动进入这里，
  管理员可确认报废（标记已报废）或恢复使用。
- 过期预警：展示「即将过期 / 已过期」的试剂瓶，便于及时处置。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from business.bottle_state import BorrowableStatus, ExpiryStatus, ScrapStatus
from components.sidebar_nav import render_sidebar
from components.auth import require_auth
from services.core.reagent_bottle_service import reagent_bottle_service
from utils.error_handler import logger
from utils.field_mapper import ReagentBottleField

st.set_page_config(page_title="待报废与过期预警", layout="wide")

if not require_auth():
    st.stop()

render_sidebar()

st.title("🗑️ 待报废与过期预警")
st.caption("空瓶（归还比例 0%）自动进入待报废清单；过期预警集中展示即将过期与已过期的试剂。")

is_admin = bool(st.session_state.get("is_admin", False))

# ---------- 汇总 ----------
_bottles = reagent_bottle_service.get_all_parsed()
pending_scrap = [
    b for b in _bottles
    if getattr(b, "scrap_flag", None) == ScrapStatus.PENDING
]
scrapped = [
    b for b in _bottles
    if getattr(b, "scrap_flag", None) == ScrapStatus.SCRAPPED
]
expiring = [
    b for b in _bottles
    if getattr(b, "expired_flag", None) == ExpiryStatus.EXPIRING
]
expired = [
    b for b in _bottles
    if getattr(b, "expired_flag", None) == ExpiryStatus.EXPIRED
]

col1, col2, col3, col4 = st.columns(4)
col1.metric("🗑️ 待报废", len(pending_scrap))
col2.metric("✅ 已报废", len(scrapped))
col3.metric("⚠️ 即将过期", len(expiring))
col4.metric("❌ 已过期", len(expired))

st.divider()

tab_scrap, tab_expiry = st.tabs(["🗑️ 待报废清单", "⏰ 过期预警"])

# ==================== 1. 待报废清单 ====================
with tab_scrap:
    if not pending_scrap:
        st.info("暂无待报废试剂瓶。归还时把「归还比例」调到 0%（空瓶），该瓶会自动进入这里。")
    else:
        if not is_admin:
            st.caption("只读视图：确认报废 / 恢复使用需管理员及以上权限。")

        # ---------- 全选 / 取消全选 ----------
        _select_all = bool(st.session_state.get("scrap_select_all", False))
        col_selall, col_selhint = st.columns([1, 3])
        with col_selall:
            if st.button(
                "☑️ 取消全选" if _select_all else "☑️ 全选",
                use_container_width=True,
                disabled=not is_admin,
                key="scrap_select_all_btn",
            ):
                st.session_state["scrap_select_all"] = not _select_all
                st.rerun()
        with col_selhint:
            st.caption(
                f"共 {len(pending_scrap)} 瓶待报废"
                + ("（当前已全选，可再次点击取消）" if _select_all else "")
            )

        _scrap_rows = [
            {
                "选择": _select_all,
                "编号": b.bottle_number,
                "名称": b.reagent_name or "-",
                "CAS号": b.cas_number or "-",
                "剩余量": float(b.remaining_quantity or 0),
                "规格": b.specification or "-",
                "存储位置": b.storage_location or "-",
                "过期状态": b.expired_flag or "正常",
                "_id": b.id,
            }
            for b in pending_scrap
        ]
        _edited = st.data_editor(
            _scrap_rows,
            column_config={
                "选择": st.column_config.CheckboxColumn("选择", default=False),
                "剩余量": st.column_config.NumberColumn(disabled=True),
                "_id": None,
            },
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"scrap_table_{_select_all}",
            disabled=not is_admin,
        )

        _selected_ids = [row["_id"] for row in _edited if row["选择"]] if is_admin else []

        col_scrap, col_restore = st.columns(2)
        with col_scrap:
            if st.button(
                "✅ 确认报废",
                type="primary",
                use_container_width=True,
                disabled=not is_admin,
                key="scrap_confirm_btn",
            ):
                if not _selected_ids:
                    st.warning("请先勾选要报废的试剂瓶")
                else:
                    _ok = 0
                    for _rid in _selected_ids:
                        if reagent_bottle_service.update(
                            _rid, {ReagentBottleField.SCRAP_FLAG: ScrapStatus.SCRAPPED}
                        ):
                            _ok += 1
                    logger.info("确认报废完成", count=_ok)
                    st.success(f"✅ 已确认报废 {_ok} 瓶")
                    st.rerun()

        with col_restore:
            if st.button(
                "↩️ 恢复使用",
                use_container_width=True,
                disabled=not is_admin,
                key="scrap_restore_btn",
            ):
                if not _selected_ids:
                    st.warning("请先勾选要恢复的试剂瓶")
                else:
                    _ok = 0
                    for _bottle in pending_scrap:
                        if _bottle.id not in _selected_ids:
                            continue
                        _qty = float(_bottle.remaining_quantity or 0)
                        if reagent_bottle_service.update(_bottle.id, {
                            ReagentBottleField.SCRAP_FLAG: None,
                            ReagentBottleField.BORROWABLE_FLAG: (
                                BorrowableStatus.BORROWABLE if _qty > 0
                                else BorrowableStatus.DEPLETED
                            ),
                        }):
                            _ok += 1
                    logger.info("恢复使用完成", count=_ok)
                    st.success(f"↩️ 已恢复 {_ok} 瓶（状态按剩余量重算）")
                    st.rerun()

    # 已报废历史
    if scrapped:
        with st.expander(f"已报废记录（{len(scrapped)} 瓶）", expanded=False):
            st.dataframe(
                [
                    {
                        "编号": b.bottle_number,
                        "名称": b.reagent_name or "-",
                        "CAS号": b.cas_number or "-",
                        "剩余量": b.remaining_quantity or 0,
                        "存储位置": b.storage_location or "-",
                        "状态": b.scrap_flag,
                    }
                    for b in scrapped
                ],
                use_container_width=True,
                hide_index=True,
            )

# ==================== 2. 过期预警 ====================
with tab_expiry:
    _watch = expired + expiring
    if not _watch:
        st.info("暂无即将过期或已过期的试剂")
    else:
        if expired:
            st.error(f"❌ 已过期 {len(expired)} 瓶，建议尽快处置或报废")
        if expiring:
            st.warning(f"⚠️ 即将过期 {len(expiring)} 瓶，请及时使用或安排处置")

        st.dataframe(
            [
                {
                    "编号": b.bottle_number,
                    "名称": b.reagent_name or "-",
                    "CAS号": b.cas_number or "-",
                    "剩余量": b.remaining_quantity or 0,
                    "规格": b.specification or "-",
                    "过期状态": b.expired_flag or "正常",
                    "是否待报废": b.scrap_flag or "-",
                    "存储位置": b.storage_location or "-",
                    "可借状态": b.borrowable_flag or "-",
                }
                for b in _watch
            ],
            use_container_width=True,
            hide_index=True,
        )
