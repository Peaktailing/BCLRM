"""系统设置页面

提供用户管理功能。
"""
import sys
import os
import re

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from components.sidebar_nav import render_sidebar
from components.auth import require_auth, require_admin
from db.database import db
from services.base.person_service import person_service
from utils.error_handler import logger

# 表名安全校验正则：仅允许字母、数字、下划线
_TABLE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')

DEFAULT_USER_PASSWORD = "926495@ph"


def main():
    """主函数：系统设置页面"""
    st.set_page_config(page_title="系统设置", layout="wide")
    st.title("⚙️ 系统设置")

    # 认证检查
    if not require_auth():
        st.stop()

    # 使用统一的侧边栏导航
    render_sidebar()

    # ========== 用户管理（需要管理员权限） ==========
    if not require_admin():
        st.stop()

    # 标签切换
    tab1, tab2 = st.tabs(["👥 用户管理", "🗄️ 数据库查看"])

    with tab1:
        st.subheader("用户管理")

        # 添加用户表单
        with st.form("add_user_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_user_name = st.text_input("用户名*", help="要添加的用户名")
            with col2:
                user_role = st.selectbox(
                    "用户角色*",
                    options=[
                        ("普通用户", "user"),
                        ("教师", "teacher"),
                        ("管理员", "admin"),
                        ("超级管理员", "super_admin"),
                    ],
                    format_func=lambda x: x[0],
                    help="选择用户角色"
                )

            col3, col4 = st.columns(2)
            with col3:
                user_department = st.text_input("部门", help="可选，用户所属部门")
            with col4:
                user_phone = st.text_input("电话", help="可选，用户联系电话")

            submitted = st.form_submit_button("添加用户", type="primary", use_container_width=True)

            if submitted:
                if not new_user_name or not new_user_name.strip():
                    st.error("❌ 请填写用户名")
                else:
                    existing = person_service.get_by_name(new_user_name.strip())
                    if existing:
                        st.warning(f"⚠️ 用户 {new_user_name} 已存在")
                    else:
                        role_value = user_role[1] if isinstance(user_role, tuple) else user_role
                        new_id = person_service.create_with_password(
                            name=new_user_name.strip(),
                            password=DEFAULT_USER_PASSWORD,
                            role=role_value,
                            department=user_department.strip() if user_department else None,
                            phone=user_phone.strip() if user_phone else None,
                        )
                        if new_id:
                            st.success(f"✅ 用户 {new_user_name} 添加成功！默认密码：{DEFAULT_USER_PASSWORD}")
                        else:
                            st.error("❌ 添加用户失败，请检查日志")

        st.markdown("---")

        # 显示所有用户
        st.subheader("用户列表")
        all_persons = person_service.get_all_persons()

        if all_persons:
            table_data = []
            role_labels = {
                "super_admin": "超级管理员",
                "admin": "管理员",
                "teacher": "教师",
                "user": "普通用户"
            }
            for idx, person in enumerate(all_persons, 1):
                table_data.append({
                    "序号": idx,
                    "ID": person.id,
                    "用户名": person.name,
                    "角色": role_labels.get(person.role, person.role or "普通用户"),
                    "部门": person.department or "-",
                    "电话": person.phone or "-",
                    "学号/工号": person.student_or_work_id or "-",
                    "已设密码": "✅" if person.password_hash else "❌",
                })

            st.dataframe(
                table_data,
                use_container_width=True,
                hide_index=True
            )

            # 重置密码功能
            st.markdown("---")
            st.subheader("重置用户密码")
            col_reset1, col_reset2, col_reset3 = st.columns([2, 2, 1])
            with col_reset1:
                reset_user_options = [p.name for p in all_persons]
                reset_user = st.selectbox(
                    "选择用户",
                    options=reset_user_options,
                    key="reset_user_select"
                )
            with col_reset2:
                new_password = st.text_input(
                    "新密码",
                    type="password",
                    value=DEFAULT_USER_PASSWORD,
                    key="reset_password_input"
                )
            with col_reset3:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("重置密码", type="primary", use_container_width=True):
                    if reset_user and new_password:
                        result = person_service.update_password(reset_user, new_password)
                        if result:
                            st.success(f"✅ 用户 {reset_user} 密码已重置")
                        else:
                            st.error("❌ 重置密码失败")
                    else:
                        st.warning("请选择用户并输入新密码")

        else:
            st.info("暂无用户数据")

    with tab2:
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
            logger.error(f"获取数据表列表失败: {str(e)}", exception=e)
            st.error("获取数据表列表失败，请检查数据库连接。")

        if all_tables:
            selected_table = st.selectbox(
                "选择数据表",
                options=all_tables,
                help="选择要查看的数据表"
            )

            if selected_table:
                # 安全校验：表名必须来自 sqlite_master 白名单，且通过正则验证
                if selected_table not in all_tables:
                    st.error("无效的表名")
                elif not _TABLE_NAME_PATTERN.match(selected_table):
                    st.error("表名包含非法字符")
                else:
                    try:
                        # 表名已通过白名单+正则双重校验，安全拼接
                        records = db.execute_query(f"SELECT * FROM {selected_table}")

                        if records:
                            st.info(f"📋 表 `{selected_table}` 共 {len(records)} 条记录")
                            st.dataframe(records, use_container_width=True, hide_index=True)
                        else:
                            st.warning(f"表 `{selected_table}` 中暂无数据")
                    except Exception as e:
                        logger.error(f"查询表 {selected_table} 失败: {str(e)}", exception=e)
                        st.error("查询数据表失败，请稍后重试。")
        else:
            st.warning("未找到任何数据表，请检查数据库是否已初始化")

if __name__ == "__main__":
    main()
