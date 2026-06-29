"""系统设置页面

提供用户管理功能。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from components.sidebar_nav import render_sidebar
from db.database import db


def main():
    """主函数：系统设置页面"""
    st.set_page_config(page_title="系统设置", layout="wide")
    st.title("⚙️ 系统设置")

    # 使用统一的侧边栏导航
    render_sidebar()

    # ========== 添加用户 ==========
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

    # ========== 数据库数据查看 ==========
    st.divider()
    st.subheader("🗄️ 数据库数据查看")
    st.caption("选择数据表查看其中的所有记录。")

    # 获取数据库中所有用户表
    all_tables = []
    try:
        rows = db.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        all_tables = [row["name"] for row in rows if row.get("name")]
    except Exception as e:
        st.error(f"获取数据表列表失败：{str(e)}")

    if all_tables:
        selected_table = st.selectbox(
            "选择数据表",
            options=all_tables,
            help="选择要查看的数据表"
        )

        if selected_table:
            # 白名单验证：确保表名来自 sqlite_master
            if selected_table not in all_tables:
                st.error("无效的表名")
            else:
                try:
                    records = db.execute_query(f"SELECT * FROM {selected_table}")

                    if records:
                        st.info(f"📋 表 `{selected_table}` 共 {len(records)} 条记录")
                        st.dataframe(records, use_container_width=True, hide_index=True)
                    else:
                        st.warning(f"表 `{selected_table}` 中暂无数据")
                except Exception as e:
                    st.error(f"查询表 `{selected_table}` 失败：{str(e)}")
    else:
        st.warning("未找到任何数据表，请检查数据库是否已初始化")

if __name__ == "__main__":
    main()
