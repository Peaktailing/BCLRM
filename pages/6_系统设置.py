"""系统设置页面

提供数据库数据查看功能。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 权限控制 ──────────────────────────────────────────────
from components.auth import (
    init_auth, require_login, render_auth_sidebar,
    get_role, get_user_id, check_perm, require_perm,
    can_add_reagent, can_edit_reagent, can_delete_reagent,
    can_borrow, can_approve, can_approve_bottle,
    can_manage_users, can_system_settings,
)
import streamlit as st
from db.database import db


def main():
    """主函数：系统设置页面"""
    st.set_page_config(page_title="系统设置", layout="wide")
    st.title("⚙️ 系统设置")

    # 使用统一的侧边栏导航
    init_auth()
    if not require_login():
        st.stop()
    render_auth_sidebar()

    if not require_perm(can_system_settings, error_msg="仅超级管理员可以访问系统设置"):
        st.stop()

    # ── 人员管理入口 ──
    st.subheader("👥 人员管理")
    st.markdown("管理用户信息，包括新增、编辑、删除用户，以及设置手机号和密码强度要求。")
    st.page_link("pages/9_人员管理.py", label="进入人员管理", icon="👥", use_container_width=True)

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
