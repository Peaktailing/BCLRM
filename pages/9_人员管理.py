"""人员信息管理页面

超级管理员专用：查看、新增、编辑、删除用户。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 权限控制 ──────────────────────────────────────────────
from components.auth import (
    init_auth, require_login, render_auth_sidebar,
    get_role, get_user_id, require_perm,
    can_manage_users,
)
from business.permission_service import ROLE_LABELS, ROLE_LEVELS
from business.password_validator import validate_password_strength, validate_phone
from services.base.person_service import person_service
import streamlit as st


def main():
    st.set_page_config(page_title="人员信息管理", page_icon="👥", layout="wide")
    st.title("👥 人员信息管理")

    # 统一侧边栏 + 登录守卫
    init_auth()
    if not require_login():
        st.stop()
    render_auth_sidebar()

    if not require_perm(can_manage_users, error_msg="仅超级管理员可以管理用户"):
        st.stop()

    # ── 角色选项 ──────────────────────────────────────────
    role_options = list(ROLE_LEVELS.keys())
    role_labels = {r: ROLE_LABELS.get(r, r) for r in role_options}

    # ── 顶部：新增用户表单 ──────────────────────────────────
    with st.expander("➕ 新增用户", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            new_user_id = st.text_input("用户ID *", placeholder="如: AD003", key="new_uid")
            new_name = st.text_input("姓名 *", key="new_name")
            new_display_name = st.text_input("显示名称", key="new_dn")
        with col2:
            new_work_id = st.text_input("工号（登录用）*", placeholder="如: zhang", key="new_wid")
            new_password = st.text_input("密码 *", type="password",
                                         placeholder="8位以上，含大小写字母+数字+符号",
                                         key="new_pwd")
            new_role = st.selectbox("角色 *", options=role_options,
                                    format_func=lambda r: role_labels[r],
                                    key="new_role")
        with col3:
            new_department = st.text_input("部门", key="new_dept")
            new_phone = st.text_input("手机号", placeholder="1 开头的11位数字",
                                      key="new_phone")

        if st.button("添加用户", type="primary", use_container_width=True):
            errors = []
            if not new_user_id.strip():
                errors.append("用户ID不能为空")
            if not new_name.strip():
                errors.append("姓名不能为空")
            if not new_work_id.strip():
                errors.append("工号不能为空")
            if not new_password.strip():
                errors.append("密码不能为空")

            if new_phone.strip():
                valid, msg = validate_phone(new_phone.strip())
                if not valid:
                    errors.append(msg)

            if new_password.strip():
                valid, msg = validate_password_strength(new_password.strip())
                if not valid:
                    errors.append(msg)

            if errors:
                for e in errors:
                    st.error(f"❌ {e}")
            else:
                success, msg, _ = person_service.create_user({
                    "user_id": new_user_id.strip(),
                    "name": new_name.strip(),
                    "password": new_password.strip(),
                    "role": new_role,
                    "department": new_department.strip(),
                    "phone": new_phone.strip(),
                    "student_or_work_id": new_work_id.strip(),
                    "display_name": new_display_name.strip() or new_name.strip(),
                })
                if success:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

    # ── 用户列表 ──────────────────────────────────────────
    st.subheader("📋 用户列表")

    users = person_service.get_all_users()

    if not users:
        st.info("暂无用户数据")
        st.stop()

    # 构建表格，密码列脱敏显示
    table_data = []
    for u in users:
        table_data.append({
            "用户ID": u.get("user_id", ""),
            "姓名": u.get("name", ""),
            "显示名称": u.get("display_name", ""),
            "角色": role_labels.get(u.get("role", ""), u.get("role", "")),
            "部门": u.get("department", "") or "-",
            "工号": u.get("student_or_work_id", "") or "-",
            "手机号": u.get("phone", "") or "-",
            "密码": "******",
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)

    # ── 编辑/删除用户 ──────────────────────────────────────
    st.divider()
    st.subheader("✏️ 编辑 / 删除用户")

    user_options = {f"{u.get('display_name', u.get('name'))} ({u.get('user_id')})": u.get("user_id")
                    for u in users}
    selected_label = st.selectbox(
        "选择要操作的用户",
        options=[""] + list(user_options.keys()),
        key="edit_user_select"
    )

    if selected_label:
        target_uid = user_options[selected_label]
        target_user = person_service.get_by_user_id(target_uid)
        if not target_user:
            st.error("用户不存在")
            st.stop()

        tab1, tab2 = st.tabs(["✏️ 编辑", "🗑️ 删除"])

        # ── 编辑 Tab ──
        with tab1:
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                edit_name = st.text_input("姓名", value=target_user.get("name", ""),
                                          key="edit_name")
                edit_dn = st.text_input("显示名称",
                                        value=target_user.get("display_name", ""),
                                        key="edit_dn")
            with col_b:
                edit_work_id = st.text_input("工号",
                                             value=target_user.get("student_or_work_id", ""),
                                             key="edit_wid")
                edit_role = st.selectbox(
                    "角色", options=role_options,
                    index=role_options.index(target_user.get("role", "student"))
                    if target_user.get("role") in role_options else 0,
                    format_func=lambda r: role_labels[r],
                    key="edit_role"
                )
            with col_c:
                edit_dept = st.text_input("部门",
                                          value=target_user.get("department", ""),
                                          key="edit_dept")
                edit_phone = st.text_input("手机号",
                                           value=target_user.get("phone", ""),
                                           key="edit_phone")

            # 重置密码（可选）
            with st.expander("🔒 修改密码（可选）", expanded=False):
                edit_new_pwd = st.text_input("新密码",
                                             type="password",
                                             placeholder="留空则不修改密码",
                                             key="edit_pwd")
                edit_pwd_confirm = st.text_input("确认新密码",
                                                 type="password",
                                                 key="edit_pwd2")

            if st.button("保存修改", type="primary", key="save_edit"):
                update_data = {}
                update_data["name"] = edit_name.strip()
                update_data["display_name"] = edit_dn.strip() or edit_name.strip()
                update_data["student_or_work_id"] = edit_work_id.strip()
                update_data["role"] = edit_role
                update_data["department"] = edit_dept.strip()
                update_data["phone"] = edit_phone.strip()

                # 密码修改
                if edit_new_pwd:
                    if edit_new_pwd != edit_pwd_confirm:
                        st.error("❌ 两次输入的密码不一致")
                        st.stop()
                    valid, msg = validate_password_strength(edit_new_pwd)
                    if not valid:
                        st.error(f"❌ 密码校验失败: {msg}")
                        st.stop()
                    update_data["password"] = edit_new_pwd

                success, msg = person_service.update_user(target_uid, update_data)
                if success:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

        # ── 删除 Tab ──
        with tab2:
            st.warning(f"⚠️ 确定要删除用户 **{target_user.get('display_name', target_user.get('name'))}** "
                       f"({target_user.get('user_id')}) 吗？此操作不可撤销。")

            if st.button("确认删除", type="secondary", key="confirm_delete"):
                success, msg = person_service.delete_user(target_uid)
                if success:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")


if __name__ == "__main__":
    main()