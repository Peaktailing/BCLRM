"""系统设置页面

提供用户管理功能。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from components.auth import init_auth, require_login, render_auth_sidebar, require_perm, can_system_settings

def main():
    """主函数：系统设置页面"""
    st.set_page_config(page_title="系统设置", layout="wide")
    st.title("⚙️ 系统设置")

    init_auth()
    if not require_login():
        st.stop()
    render_auth_sidebar()

    if not require_perm(can_system_settings, error_msg="您没有系统设置的权限，请联系管理员"):
        st.stop()

    # 添加用户功能
    st.subheader("添加用户")
    st.info("💡 添加普通用户，权限问题后续再处理")

    with st.form("add_user_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_user_name = st.text_input("用户名*", help="要添加的用户名")
        with col2:
            user_role = st.selectbox(
                "用户角色*",
                options=["普通用户"],
                disabled=True,
                help="暂时只支持添加普通用户"
            )

        submitted = st.form_submit_button("添加用户", type="primary", use_container_width=True)

        if submitted:
            if not new_user_name or not new_user_name.strip():
                st.error("❌ 请填写用户名")
            else:
                # 临时保存到session_state
                if "user_list" not in st.session_state:
                    st.session_state.user_list = []
                if new_user_name not in st.session_state.user_list:
                    st.session_state.user_list.append(new_user_name.strip())
                    st.success(f"✅ 用户 {new_user_name} 添加成功！")
                else:
                    st.warning(f"⚠️ 用户 {new_user_name} 已存在")

    # 显示已添加的用户
    if "user_list" in st.session_state and st.session_state.user_list:
        st.markdown("---")
        st.subheader("已添加用户")
        st.dataframe(
            [{"序号": i+1, "用户名": name} for i, name in enumerate(st.session_state.user_list)],
            use_container_width=True,
            hide_index=True
        )

if __name__ == "__main__":
    main()
