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
import secrets

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from business.evidence_service import PHASE_BORROW, PHASE_RETURN, evidence_service
from components.sidebar_nav import render_sidebar
from components.auth import require_auth, require_super_admin, require_admin
from utils.password_utils import hash_password
from services.base.person_service import person_service
from services.base.operation_log_service import operation_log_service
from services.base.system_config_service import EvidenceConfig, system_config_service
from services.core.borrow_record_service import borrow_record_service
from services.core.return_record_service import return_record_service
from db.database import db
from utils.audit import audit
from utils.error_handler import logger

# 表名安全校验正则：仅允许字母、数字、下划线
_TABLE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')


def _estimate_photo(edge: int, quality: int) -> str:
    """粗估单张照片体积。

    只用来回答「这个旋钮往哪边拧、能省多少」——照片体积随画面内容（噪点、
    细节）浮动接近一倍，任何精确公式都是假的。按 1280 px / q75 ≈ 235 KB
    标定（实测一张 4000×3000 手机原图，内容偏碎的偏高值），
    像素数平方缩放、质量按每 +6 涨 1.18 倍。
    """
    pixels = (float(edge) / 1280.0) ** 2
    grade = 1.18 ** ((float(quality) - 75.0) / 6.0)
    return f"约 {235 * pixels * grade:.0f} KB"

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
    st.info("💡 新用户将生成一次性随机初始密码；请当场转告并提醒首次登录后立即修改。")

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
                _initial_pwd = "Rst" + secrets.token_urlsafe(6)
                new_id = person_service.create({
                    "name": name,
                    "role": _ROLE_OPTIONS[role_label],
                    "password_hash": hash_password(_initial_pwd),
                })
                if new_id:
                    st.success(
                        f"✅ 用户 {name} 添加成功！初始密码（仅显示一次）：{_initial_pwd}"
                    )
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
                elif target and (
                    borrow_record_service.get_all_by_field("user", rename_target)
                    or return_record_service.get_all_by_field("return_user", rename_target)
                ):
                    # borrow_record.user / return_record.return_user 对 person(name) 有外键
                    st.error("❌ 该用户已有领用 / 归还记录，暂不支持改名（外键关联）")
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
            st.caption("重置后生成一次性随机密码，仅显示一次，请立即转告该用户并嘱其尽快修改。")
            if st.button("生成随机密码并重置", key="reset_btn", use_container_width=True):
                target = person_service.get_by_name(reset_target)
                if not target:
                    st.error("❌ 用户不存在")
                else:
                    _new_pwd = "Rst" + secrets.token_urlsafe(6)
                    if person_service.update(
                        target.id, {"password_hash": hash_password(_new_pwd)}
                    ):
                        st.success(
                            f"✅ 已重置 {reset_target} 的密码，新密码（仅显示一次）：{_new_pwd}"
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
                        audit(
                            st.session_state.get("user_name", ""),
                            "删除用户",
                            target_type="user",
                            target_id=del_target,
                        )
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
                audit(
                    st.session_state.get("user_name", ""),
                    "修改角色",
                    target_type="user",
                    target_id=role_target,
                    detail=f"{target.role or '-'} → {new_role}",
                )
                st.success(f"✅ 已将 {role_target} 的角色改为「{role_label}」")
                st.rerun()
            else:
                st.error("❌ 修改角色失败，请重试")

    # ========== 现场取证（手机拍照） ==========
    st.divider()
    st.subheader("📷 现场取证")
    st.caption(
        "借出与归还时的拍照留证。**必拍开关放在这里，是因为「拍不拍」"
        "是这个实验室的危化品管理口径，不是软件该替人决定的事**——"
        "学期初可能收紧，期末可能放宽，改一次不该发一次版。"
    )

    _ev_require_borrow = evidence_service.require(PHASE_BORROW)
    _ev_require_return = evidence_service.require(PHASE_RETURN)
    _ev_max_mb = evidence_service.max_mb()
    _ev_max_edge = evidence_service.max_edge()
    _ev_quality = evidence_service.quality()
    _ev_base_url = system_config_service.get(EvidenceConfig.MOBILE_BASE_URL, "")

    with st.form("evidence_settings"):
        _c1, _c2 = st.columns(2)
        with _c1:
            _new_require_borrow = st.checkbox(
                "借出必须拍照",
                value=_ev_require_borrow,
                help="打开后，「批准并执行领用」前必须上传发料现场照片",
            )
        with _c2:
            _new_require_return = st.checkbox(
                "归还必须拍照",
                value=_ev_require_return,
                help="打开后，「提交归还」前必须上传回库照片（剩余量、瓶身状态）",
            )
        _c3, _c4 = st.columns(2)
        with _c3:
            _new_max_mb = st.number_input(
                "单张照片上限（MB）",
                min_value=1,
                max_value=50,
                value=int(_ev_max_mb),
                step=1,
                help="压缩后仍超过这个体积就拒绝入库（防的是异常文件，不是正常照片）",
            )
        with _c4:
            _new_base_url = st.text_input(
                "手机访问地址",
                value=_ev_base_url,
                placeholder="http://192.168.1.10:8601",
                help=(
                    "填了之后，瓶身二维码里是一条 URL，手机用系统相机或微信扫一扫"
                    "就能直接打开取证页；不填则二维码里是短码，需要用取证页的摄像头扫"
                ),
            )
        _c5, _c6, _c7 = st.columns(3)
        with _c5:
            _new_max_edge = st.number_input(
                "照片长边（像素）",
                min_value=640,
                max_value=4096,
                value=int(_ev_max_edge),
                step=64,
                help="越小越省空间，也越看不清标签上的小字。1440 约 180–260 KB",
            )
        with _c6:
            _new_quality = st.slider(
                "JPEG 质量",
                min_value=40,
                max_value=95,
                value=int(_ev_quality),
                step=1,
                help="78 与 85 肉眼看不出差别，体积差三成",
            )
        with _c7:
            st.metric(
                "单张预计体积",
                _estimate_photo(_new_max_edge, _new_quality),
                help="按常见手机照片估算，实际随画面复杂度浮动",
            )
        if st.form_submit_button("保存取证设置", type="primary"):
            _operator = st.session_state.get("user_name", "")
            _saved = system_config_service.set_many(
                {
                    EvidenceConfig.REQUIRE_BORROW: "1" if _new_require_borrow else "0",
                    EvidenceConfig.REQUIRE_RETURN: "1" if _new_require_return else "0",
                    EvidenceConfig.MAX_MB: str(int(_new_max_mb)),
                    EvidenceConfig.PHOTO_MAX_EDGE: str(int(_new_max_edge)),
                    EvidenceConfig.PHOTO_QUALITY: str(int(_new_quality)),
                    EvidenceConfig.MOBILE_BASE_URL: (_new_base_url or "").strip(),
                },
                _operator,
            )
            if _saved:
                st.success(f"✅ 已保存 {_saved} 项取证设置")
                st.rerun()
            else:
                st.error("❌ 保存失败，请重试")

    st.caption(
        "取证明细：借出照片挂在工单上（`evidence_borrow`），归还照片同挂工单"
        "（`evidence_return`）。一张单两个阶段互不覆盖，查单时都能看到。"
        "手机端入口：`/m`，或扫瓶身二维码。"
    )

    # ========== 数据库数据查看 ==========
    st.divider()
    st.subheader("🗄️ 数据库数据查看")
    st.caption("选择数据表查看其中的所有记录。此功能仅限超级管理员使用。")

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

    # ---------- 📜 审计日志 ----------
    st.divider()
    st.subheader("📜 审计日志")
    st.caption("记录关键操作（登录/领用/归还/审批等）留痕；最多展示最近 200 条，按时间倒序。")

    _log_action = st.selectbox(
        "操作类型",
        options=[
            "全部", "登录", "领用", "归还", "发起工单", "提交审批",
            "审批通过", "驳回工单", "工单归还", "修改密码",
        ],
        key="audit_action_filter",
    )
    _log_operator = st.text_input(
        "操作人（留空查看全部）", key="audit_operator_filter"
    )

    _logs = operation_log_service.list_logs(
        action=None if _log_action == "全部" else _log_action,
        operator=_log_operator.strip() or None,
        limit=200,
    )
    if _logs:
        st.dataframe(
            [
                {
                    "时间": row.get("created_at"),
                    "操作人": row.get("operator"),
                    "操作": row.get("action"),
                    "目标": f"{row.get('target_type') or ''} {row.get('target_id') or ''}".strip(),
                    "详情": row.get("detail") or "",
                }
                for row in _logs
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"共 {len(_logs)} 条记录")
    else:
        st.info("暂无审计日志记录")


if __name__ == "__main__":
    main()
