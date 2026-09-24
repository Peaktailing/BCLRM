"""系统设置页面（仅超级管理员可见/可用）

功能：
- 添加用户：写入 person 表（支持角色），初始密码统一为默认初始密码
- 查看已添加用户：从 person 表读取
- 数据库数据查看：管理员及以上

权限：本页仅在超级管理员的导航中注册；此外页面内再做一次 require_super_admin()
校验，确保即使通过 URL 直达也会被拦截。
"""
import sys
import os
import re

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from components.sidebar_nav import render_sidebar
from components.auth import require_auth, require_super_admin, require_admin
from config.settings import DEFAULT_INITIAL_PASSWORD
from services.base.person_service import person_service
from services.core.borrow_record_service import borrow_record_service
from services.core.return_record_service import return_record_service
from db.database import db
from utils.error_handler import logger

# 表名安全校验正则：仅允许字母、数字、下划线
_TABLE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')

# 可选角色：显示名 -> 存储值（超级管理员不开放自助添加）
_ROLE_OPTIONS = {
    "普通用户": "user",
    "教师": "teacher",
    "管理员": "admin",
}

_ROLE_LABELS = {
    "super_admin": "超级管理员",
    "admin": "管理员",
    "teacher": "教师",
    "user": "普通用户",
}


def main():
    """主函数：系统设置页面"""
    st.set_page_config(page_title="系统设置", layout="wide")
    st.title("⚙️ 系统设置")

    # 认证检查
    if not require_auth():
        st.stop()

    # 权限检查：仅超级管理员可访问
    if not require_super_admin():
        st.stop()

    # 使用统一的侧边栏导航
    render_sidebar()

    # ========== 添加用户 ==========
    st.subheader("添加用户")
    st.info(f"💡 新用户初始密码为「{DEFAULT_INITIAL_PASSWORD}」，请提醒其首次登录后尽快修改。")

    with st.form("add_user_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_user_name = st.text_input("用户名*", help="要添加的用户名（姓名）")
        with col2:
            role_label = st.selectbox(
                "用户角色*",
                options=list(_ROLE_OPTIONS.keys()),
                help="超级管理员角色暂不开放自助添加"
            )

        submitted = st.form_submit_button("添加用户", type="primary", use_container_width=True)

        if submitted:
            name = (new_user_name or "").strip()
            if not name:
                st.error("❌ 请填写用户名")
            elif person_service.get_by_name(name):
                st.warning(f"⚠️ 用户 {name} 已存在")
            else:
                new_id = person_service.create({
                    "name": name,
                    "role": _ROLE_OPTIONS[role_label],
                })
                if new_id:
                    st.success(f"✅ 用户 {name} 添加成功！（初始密码 {DEFAULT_INITIAL_PASSWORD}）")
                else:
                    st.error("❌ 添加用户失败，请重试")

    # ========== 已添加用户（来自 person 表） ==========
    persons = person_service.get_all_persons()
    if persons:
        st.markdown("---")
        st.subheader("已添加用户")
        st.dataframe(
            [
                {
                    "序号": i + 1,
                    "用户名": p.name,
                    "角色": _ROLE_LABELS.get(p.role, p.role or "-"),
                }
                for i, p in enumerate(persons)
            ],
            use_container_width=True,
            hide_index=True
        )

        # ========== 用户管理：修改用户名（登录名） / 重置密码 ==========
        st.markdown("#### 🛠️ 用户管理")
        user_names = [p.name for p in persons]

        col_rename, col_reset = st.columns(2)

        # --- 修改用户名（登录名）---
        with col_rename:
            st.markdown("**修改用户名（登录名）**")
            rename_target = st.selectbox("选择用户", options=user_names, key="rename_target")
            new_name = st.text_input("新用户名", key="rename_new_name")
            if st.button("保存用户名", key="rename_btn", use_container_width=True):
                new_name_clean = (new_name or "").strip()
                target = person_service.get_by_name(rename_target)
                if not new_name_clean:
                    st.error("❌ 请输入新用户名")
                elif new_name_clean == rename_target:
                    st.warning("⚠️ 新用户名与原用户名相同")
                elif person_service.get_by_name(new_name_clean):
                    st.error(f"❌ 用户名 {new_name_clean} 已存在")
                elif target and person_service.update(target.id, {"name": new_name_clean}):
                    # 若修改的是当前登录用户，同步会话中的用户名，避免后续鉴权失效
                    if st.session_state.get("user_name") == rename_target:
                        st.session_state["user_name"] = new_name_clean
                    st.success(f"✅ 用户名已由 {rename_target} 改为 {new_name_clean}")
                    st.rerun()
                else:
                    st.error("❌ 修改用户名失败，请重试")

        # --- 重置密码 ---
        with col_reset:
            st.markdown("**重置密码**")
            reset_target = st.selectbox("选择用户", options=user_names, key="reset_target")
            st.caption(f"重置后该用户密码恢复为初始密码「{DEFAULT_INITIAL_PASSWORD}」。")
            if st.button("重置为初始密码", key="reset_btn", use_container_width=True):
                target = person_service.get_by_name(reset_target)
                if target and person_service.update(target.id, {"password_hash": None}):
                    st.success(
                        f"✅ 已将 {reset_target} 的密码重置为初始密码「{DEFAULT_INITIAL_PASSWORD}」"
                    )
                else:
                    st.error("❌ 重置密码失败，请重试")

        # --- 删除用户（本页已限超级管理员）---
        st.markdown("**删除用户**")
        st.caption("删除后该用户将无法登录；若其已有领用或归还记录，则不允许删除。")
        del_target = st.selectbox("选择用户", options=user_names, key="del_user_select")
        del_confirm = st.checkbox("我确认删除该用户", key="del_user_confirm")
        if st.button("删除用户", key="del_user_btn", use_container_width=True):
            if not del_confirm:
                st.warning("⚠️ 请先勾选确认")
            elif del_target == st.session_state.get("user_name"):
                st.error("❌ 不能删除当前登录用户")
            else:
                target = person_service.get_by_name(del_target)
                if not target:
                    st.error("❌ 用户不存在")
                else:
                    borrow_refs = borrow_record_service.get_all_by_field("user", del_target)
                    return_refs = return_record_service.get_all_by_field("return_user", del_target)
                    if borrow_refs or return_refs:
                        st.error(
                            f"❌ 该用户已有 {len(borrow_refs)} 条领用 / "
                            f"{len(return_refs)} 条归还记录，无法删除"
                        )
                    elif person_service.delete(target.id):
                        st.success(f"✅ 已删除用户 {del_target}")
                        st.rerun()
                    else:
                        st.error("❌ 删除失败（可能受关联数据限制）")

        # --- 修改用户角色（本页已限超级管理员）---
        st.markdown("**修改用户角色**")
        st.caption("教师 = 授课老师；管理员 = 实验员（实验准备）。超级管理员角色不在此处调整。")
        col_role_user, col_role_pick = st.columns(2)
        with col_role_user:
            role_target = st.selectbox("选择用户", options=user_names, key="role_target")
        with col_role_pick:
            role_label = st.selectbox(
                "新角色",
                options=["普通用户", "教师", "管理员"],
                key="role_new"
            )
        if st.button("保存角色", key="role_btn", use_container_width=True):
            target = person_service.get_by_name(role_target)
            new_role = _ROLE_OPTIONS[role_label]
            if not target:
                st.error("❌ 用户不存在")
            elif target.role == "super_admin":
                st.warning("⚠️ 超级管理员的角色不可在此修改")
            elif st.session_state.get("user_name") == role_target:
                st.error("❌ 不能修改当前登录用户自己的角色")
            elif person_service.update(target.id, {"role": new_role}):
                st.success(f"✅ 已将 {role_target} 的角色改为「{role_label}」")
                st.rerun()
            else:
                st.error("❌ 修改角色失败，请重试")

    # ========== 数据库数据查看 ==========
    st.divider()
    st.subheader("🗄️ 数据库数据查看")
    st.caption("选择数据表查看其中的所有记录。此功能仅限管理员使用。")

    # 管理员权限检查
    if not require_admin():
        st.stop()

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
