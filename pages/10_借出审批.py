"""借出审批页面 - 仅管理员/超级管理员可见

审批内容：
- 教师提交的借出工单
- 教师提交的还入工单

工单 vs 瓶子模式说明：
- 工单是审批容器：教师一次提交多瓶试剂→管理员审批
- 瓶子独立跟踪：A借出、B归还，每个瓶子独立记录状态
- 审批通过后自动执行借出/归还操作
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from components.auth import (
    init_auth, require_login, render_auth_sidebar,
    get_user, get_role, get_user_id, require_perm,
    can_approve,
)
from business.work_order_service import work_order_service
from business.permission_service import get_role_label


def main():
    st.set_page_config(page_title="借出审批", page_icon="✅", layout="wide")
    st.title("✅ 借出/还入审批")

    init_auth()
    if not require_login():
        st.stop()
    render_auth_sidebar()

    if not require_perm(can_approve, error_msg="仅管理员可以进行审批操作"):
        st.stop()

    user = get_user()
    approver_id = get_user_id()

    tab1, tab2 = st.tabs(["📥 借出审批", "📤 还入审批"])

    # ── 借出审批 Tab ──
    with tab1:
        st.subheader("待审批借出工单")
        pending_orders = work_order_service.get_pending_borrow_orders()

        if not pending_orders:
            st.info("暂无待审批的借出工单")
        else:
            for order in pending_orders:
                with st.expander(
                    f"工单 {order['order_number']} | 申请人: {order['applicant_name']} | "
                    f"提交时间: {order.get('created_at', '')}",
                    expanded=False
                ):
                    st.markdown(f"**申请人**: {order['applicant_name']}")
                    st.markdown(f"**备注**: {order.get('remark', '无')}")

                    if order.get("items"):
                        st.markdown("**工单项明细**:")
                        item_data = []
                        for item in order["items"]:
                            item_data.append({
                                "试剂瓶编号": item["bottle_number"],
                                "借出数量": f"{item['borrow_qty']}g",
                                "状态": item["status"],
                            })
                        st.dataframe(item_data, use_container_width=True, hide_index=True)

                    col_a, col_r = st.columns(2)
                    with col_a:
                        if st.button(f"✅ 批准", key=f"approve_borrow_{order['id']}",
                                     type="primary", use_container_width=True):
                            result = work_order_service.approve_borrow_order(order["id"], approver_id)
                            if result.is_success():
                                st.success(result.message)
                                st.rerun()
                            else:
                                st.error(result.message)
                    with col_r:
                        if st.button(f"❌ 拒绝", key=f"reject_borrow_{order['id']}",
                                     use_container_width=True):
                            result = work_order_service.reject_borrow_order(order["id"], approver_id)
                            if result.is_success():
                                st.warning(result.message)
                                st.rerun()
                            else:
                                st.error(result.message)

    # ── 还入审批 Tab ──
    with tab2:
        st.subheader("待审批还入工单")
        pending_returns = work_order_service.get_pending_return_orders()

        if not pending_returns:
            st.info("暂无待审批的还入工单")
        else:
            for order in pending_returns:
                with st.expander(
                    f"工单 {order['order_number']} | 申请人: {order['applicant_name']} | "
                    f"提交时间: {order.get('created_at', '')}",
                    expanded=False
                ):
                    st.markdown(f"**申请人**: {order['applicant_name']}")
                    st.markdown(f"**备注**: {order.get('remark', '无')}")

                    if order.get("items"):
                        st.markdown("**工单项明细**:")
                        item_data = []
                        for item in order["items"]:
                            item_data.append({
                                "试剂瓶编号": item["bottle_number"],
                                "归还数量": f"{item['return_qty']}g",
                                "状态": item["status"],
                            })
                        st.dataframe(item_data, use_container_width=True, hide_index=True)

                    col_a, col_r = st.columns(2)
                    with col_a:
                        if st.button(f"✅ 批准", key=f"approve_return_{order['id']}",
                                     type="primary", use_container_width=True):
                            result = work_order_service.approve_return_order(order["id"], approver_id)
                            if result.is_success():
                                st.success(result.message)
                                st.rerun()
                            else:
                                st.error(result.message)
                    with col_r:
                        if st.button(f"❌ 拒绝", key=f"reject_return_{order['id']}",
                                     use_container_width=True):
                            result = work_order_service.reject_return_order(order["id"], approver_id)
                            if result.is_success():
                                st.warning(result.message)
                                st.rerun()
                            else:
                                st.error(result.message)


if __name__ == "__main__":
    main()