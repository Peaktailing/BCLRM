"""
四层分级权限系统 v2 - Streamlit 演示应用

用户认证：工号 + 密码登录
未登录状态 = 学生权限（仅查看）
审批逻辑：试剂瓶所属管理员审批自己瓶子的借出申请
"""

import streamlit as st
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from models import init_db, seed_data, User, ReagentBottle, BorrowRecord
from data import (
    login, get_user, get_all_users, get_users_by_role,
    get_all_bottles, get_bottles_by_creator, get_bottle_by_number,
    add_bottle, update_bottle, delete_bottle,
    get_all_borrow_records, get_borrow_records_by_borrower,
    get_pending_borrows_for_admin, create_borrow_record, approve_borrow,
    get_next_bottle_number, get_next_record_number,
    add_user, delete_user, get_admin_ids_for_user, get_admin_users_for_user,
    get_user_ids_for_admin, get_users_for_admin, add_user_admin_relation,
    remove_user_admin_relation,
)
from core import (
    get_role_level, get_role_label,
    can_view_reagents, can_add_reagent, can_edit_reagent, can_delete_reagent,
    can_borrow_reagent, can_approve_borrow, can_approve_bottle,
    can_manage_users, can_system_settings,
    PERMISSION_DESCRIPTIONS, ROLE_LABELS_ZH,
)


# ── 页面配置 ──────────────────────────────────────────────

st.set_page_config(
    page_title="权限系统演示 - 试剂管理",
    page_icon="🧪",
    layout="wide",
)


# ── Session 状态 ──────────────────────────────────────────

def init_session():
    if "user" not in st.session_state:
        st.session_state.user = None


init_session()


# ── 初始化数据库 ──────────────────────────────────────────

@st.cache_resource
def init_database():
    # 删除旧库重新初始化（演示环境）
    db_path = os.path.join(os.path.dirname(__file__), "permission_demo.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db()
    seed_data()
    return True


init_database()


# ── 辅助函数 ──────────────────────────────────────────────

def get_current_user() -> User | None:
    return st.session_state.user


def get_current_role() -> str:
    if st.session_state.user:
        return st.session_state.user.role
    return "student"  # 未登录 = 学生


def is_logged_in() -> bool:
    return st.session_state.user is not None


def role_badge(role: str) -> str:
    colors = {
        "super_admin": "🔴",
        "admin": "🟠",
        "teacher": "🟢",
        "student": "🔵",
    }
    return f"{colors.get(role, '⚪')} {get_role_label(role)}"


def get_user_label(u: User) -> str:
    """生成用户显示标签"""
    return f"{u.display_name} ({u.work_id}) | {get_role_label(u.role)} | {u.department}"


# ── 侧边栏 - 登录/用户信息 ────────────────────────────────

with st.sidebar:
    st.title("🧪 权限系统演示")
    st.caption("四层分级权限管理 v2")

    st.divider()

    if is_logged_in():
        user = get_current_user()
        st.success(f"已登录")
        st.markdown(f"**用户:** {user.display_name}")
        st.markdown(f"**工号:** {user.work_id}")
        st.markdown(f"**角色:** {role_badge(user.role)}")
        st.markdown(f"**部门:** {user.department}")

        # 显示从属管理员
        if user.role in ("teacher", "student"):
            admins = get_admin_users_for_user(user.user_id)
            if admins:
                admin_labels = "、".join([a.display_name for a in admins])
                st.markdown(f"**从属管理员:** {admin_labels}")

        if st.button("🚪 退出登录", use_container_width=True):
            st.session_state.user = None
            st.rerun()
    else:
        st.info("当前处于**未登录状态**（学生权限 - 仅查看）")

        with st.expander("🔑 工号登录", expanded=True):
            with st.form("login_form"):
                work_id = st.text_input("工号", placeholder="如: zhang, wang, root")
                password = st.text_input("密码", type="password", placeholder="默认: 123456")
                submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

                if submitted:
                    if not work_id.strip():
                        st.error("请输入工号")
                    else:
                        user_obj = login(work_id.strip(), password.strip() or "123456")
                        if user_obj:
                            st.session_state.user = user_obj
                            st.rerun()
                        else:
                            st.error("工号或密码错误")

        # 显示快捷账号提示
        with st.expander("💡 测试账号"):
            st.markdown("""
            | 角色 | 工号 | 密码 |
            |------|------|------|
            | 超级管理员 | root | admin123 |
            | 管理员(张) | zhang | 123456 |
            | 管理员(李) | li | 123456 |
            | 教师(王教授) | wang | 123456 |
            | 教师(赵教授) | zhao | 123456 |
            | 学生(小学生) | stu1 | 123456 |
            | 学生(中学生) | stu2 | 123456 |
            """)

    st.divider()
    st.caption("未登录 = 学生权限（仅查看）")

# ── 主界面 ────────────────────────────────────────────────

col1, col2, col3 = st.columns([1, 3, 1])
with col2:
    st.markdown(f"<h1 style='text-align: center;'>🧪 试剂库管理系统</h1>", unsafe_allow_html=True)
    role_label = get_role_label(get_current_role())
    st.markdown(
        f"<p style='text-align: center; color: gray;'>"
        f"当前角色：<strong>{role_label}</strong>"
        f"{' | 用户：' + get_current_user().display_name if is_logged_in() else ' | 未登录（学生权限）'}"
        f"</p>",
        unsafe_allow_html=True,
    )

st.divider()

# ── 权限矩阵展示 ──────────────────────────────────────────

with st.expander("📋 权限矩阵一览", expanded=False):
    cols = st.columns([2, 1, 1, 1, 1])
    headers = ["操作", "学生", "教师", "管理员", "超级管理员"]
    for col, h in zip(cols, headers):
        col.markdown(f"**{h}**")

    for action, perm_map in PERMISSION_DESCRIPTIONS.items():
        cols = st.columns([2, 1, 1, 1, 1])
        cols[0].markdown(action)
        for i, (role, val) in enumerate(perm_map.items()):
            cols[i + 1].markdown(val)

# ── Tabs 功能区 ───────────────────────────────────────────

current_role = get_current_role()
current_user = get_current_user()

tab_names = ["📦 试剂库存"]

if can_borrow_reagent(current_role)[0]:
    tab_names.append("📤 借出试剂")

if can_approve_borrow(current_role)[0]:
    tab_names.append("✅ 审批管理")

if can_add_reagent(current_role)[0]:
    tab_names.append("➕ 试剂入库")

if can_manage_users(current_role)[0]:
    tab_names.append("👥 用户管理")

if can_system_settings(current_role)[0]:
    tab_names.append("⚙️ 系统设置")

tabs = st.tabs(tab_names)

# ══════════════════════════════════════════════════════════
# Tab 1: 试剂库存
# ══════════════════════════════════════════════════════════

with tabs[0]:
    st.subheader("📦 试剂库存一览")

    bottles = get_all_bottles()

    if not bottles:
        st.info("暂无试剂数据")
    else:
        data_rows = []
        for b in bottles:
            ctrl_mark = "⚠️ 管控" if b.is_controlled else "普通"
            data_rows.append({
                "瓶号": b.bottle_number,
                "试剂名称": b.reagent_name,
                "CAS号": b.cas_number or "-",
                "规格": b.specification,
                "剩余量": f"{b.quantity} {b.unit}",
                "存储位置": b.storage_location,
                "所属管理员": b.creator_name,
                "类型": ctrl_mark,
            })

        st.dataframe(data_rows, use_container_width=True, hide_index=True)

    # 编辑/删除操作
    if bottles and is_logged_in():
        st.divider()
        st.markdown("##### 试剂操作")

        can_edit = can_edit_reagent(current_role, current_user.user_id, None)[0]
        can_del = can_delete_reagent(current_role, current_user.user_id, None)[0]

        if can_edit or can_del:
            with st.form("reagent_action_form"):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    bottle_options = {
                        f"#{b.bottle_number} - {b.reagent_name} (录入: {b.creator_name})": b.bottle_number
                        for b in bottles
                    }
                    selected_bottle = st.selectbox("选择试剂瓶", options=list(bottle_options.keys()), key="edit_select")
                    bottle_num = bottle_options[selected_bottle]
                with col_b:
                    action_type = st.selectbox("操作类型", ["编辑", "删除"])

                if st.form_submit_button("执行", use_container_width=True):
                    bottle = get_bottle_by_number(bottle_num)
                    if not bottle:
                        st.error("未找到该试剂瓶")
                    elif action_type == "编辑":
                        ok, msg = can_edit_reagent(current_role, current_user.user_id, bottle.creator)
                        if ok:
                            st.info(f"演示模式：已准备编辑试剂 #{bottle_num}（{bottle.reagent_name}）")
                            st.success(msg)
                        else:
                            st.warning(f"⛔ {msg}")
                    elif action_type == "删除":
                        ok, msg = can_delete_reagent(current_role, current_user.user_id, bottle.creator)
                        if ok:
                            if delete_bottle(bottle_num):
                                st.success(f"试剂 #{bottle_num} 已删除")
                                st.rerun()
                        else:
                            st.warning(f"⛔ {msg}")
        else:
            st.caption("当前角色无编辑/删除试剂权限")

# ══════════════════════════════════════════════════════════
# Tab 2: 借出试剂
# ══════════════════════════════════════════════════════════

if can_borrow_reagent(current_role)[0]:
    tab_idx = tab_names.index("📤 借出试剂")
    with tabs[tab_idx]:
        st.subheader("📤 借出试剂")

        col_a, col_b = st.columns([1, 1])

        with col_a:
            st.markdown("##### 发起借出申请")
            available_bottles = [b for b in get_all_bottles() if b.quantity > 0]

            with st.form("borrow_form"):
                bottle_opts = {
                    f"#{b.bottle_number} - {b.reagent_name} "
                    f"(余量: {b.quantity}{b.unit}, 管理员: {b.creator_name})": b
                    for b in available_bottles
                }
                selected = st.selectbox("选择试剂", options=list(bottle_opts.keys()), key="borrow_select")
                bottle = bottle_opts[selected]

                max_qty = bottle.quantity
                qty = st.number_input(
                    f"借出数量（最大 {max_qty} {bottle.unit}）",
                    min_value=0.1, max_value=float(max_qty), value=min(10.0, float(max_qty)), step=0.1,
                )

                submitted = st.form_submit_button("提交借出申请", type="primary", use_container_width=True)

                if submitted:
                    record_number = get_next_record_number()
                    ok = create_borrow_record(
                        record_number=record_number,
                        bottle_number=bottle.bottle_number,
                        reagent_name=bottle.reagent_name,
                        borrower_id=current_user.user_id,
                        borrower_name=current_user.display_name,
                        quantity=qty,
                    )
                    if ok:
                        st.success(f"借出申请已提交！记录编号：{record_number}")
                        st.info(f"已通知试剂瓶所属管理员（{bottle.creator_name}）审批")
                        st.rerun()
                    else:
                        st.error("提交失败，请重试")

        with col_b:
            st.markdown("##### 我的借出记录")
            my_records = get_borrow_records_by_borrower(current_user.user_id)
            if not my_records:
                st.caption("暂无借出记录")
            else:
                for r in my_records:
                    status_icon = {"待审批": "⏳", "已批准": "✅", "已拒绝": "❌"}.get(r.status, "❓")
                    st.markdown(
                        f"- {status_icon} **{r.reagent_name}** x{r.quantity} "
                        f"| {r.borrow_time} | **{r.status}**"
                        + (f" (审批人: {r.approver_name})" if r.approver_name else "")
                    )

# ══════════════════════════════════════════════════════════
# Tab 3: 审批管理（仅管理员可见，且只能审批自己瓶子的申请）
# ══════════════════════════════════════════════════════════

if can_approve_borrow(current_role)[0]:
    tab_idx = tab_names.index("✅ 审批管理")
    with tabs[tab_idx]:
        st.subheader("✅ 借出审批管理")

        # 仅显示当前管理员自己试剂瓶的待审批申请
        pending = get_pending_borrows_for_admin(current_user.user_id)

        if not pending:
            st.info("暂无针对您试剂瓶的待审批借出申请")
        else:
            st.markdown(
                f"您的试剂瓶有 **{len(pending)}** 条待审批的借出申请"
            )

            for record in pending:
                # 权限验证：当前管理员必须是该试剂瓶的创建者
                ok, msg = can_approve_bottle(
                    current_role, current_user.user_id, record["creator"]
                )
                if not ok:
                    continue

                with st.container(border=True):
                    col_a, col_b, col_c = st.columns([3, 1, 1])
                    with col_a:
                        st.markdown(
                            f"**{record['reagent_name']}** (瓶号: {record['bottle_number']}) | "
                            f"借用人: {record['borrower_name']} | "
                            f"数量: {record['quantity']} | "
                            f"时间: {record['borrow_time']}"
                        )
                    with col_b:
                        if st.button("✅ 批准", key=f"approve_{record['id']}", use_container_width=True):
                            if approve_borrow(record["id"], current_user.user_id, current_user.display_name, True):
                                st.success(f"已批准 - {record['reagent_name']}")
                                st.rerun()
                    with col_c:
                        if st.button("❌ 拒绝", key=f"reject_{record['id']}", use_container_width=True):
                            if approve_borrow(record["id"], current_user.user_id, current_user.display_name, False):
                                st.info(f"已拒绝 - {record['reagent_name']}")
                                st.rerun()

        st.divider()
        st.markdown("##### 我管理的用户")
        my_users = get_users_for_admin(current_user.user_id)
        if my_users:
            for u in my_users:
                st.markdown(f"- {u.display_name} ({get_role_label(u.role)})")
        else:
            st.caption("暂无管理的用户")

        st.divider()
        st.markdown("##### 我的试剂瓶借出记录")
        my_bottles = get_bottles_by_creator(current_user.user_id)
        my_bn = [b.bottle_number for b in my_bottles]
        all_records = get_all_borrow_records()
        my_bottle_records = [r for r in all_records if r.bottle_number in my_bn]
        if my_bottle_records:
            record_data = [{
                "记录编号": r.record_number,
                "试剂": r.reagent_name,
                "借用人": r.borrower_name,
                "数量": r.quantity,
                "借出时间": r.borrow_time,
                "状态": r.status,
                "审批人": r.approver_name or "-",
            } for r in my_bottle_records]
            st.dataframe(record_data, use_container_width=True, hide_index=True)
        else:
            st.caption("暂无借出记录")

# ══════════════════════════════════════════════════════════
# Tab 4: 试剂入库
# ══════════════════════════════════════════════════════════

if can_add_reagent(current_role)[0]:
    tab_idx = tab_names.index("➕ 试剂入库")
    with tabs[tab_idx]:
        st.subheader("➕ 新增试剂瓶")

        with st.form("add_bottle_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                reagent_name = st.text_input("试剂名称 *", placeholder="如：无水乙醇")
                cas_number = st.text_input("CAS 号", placeholder="如：64-17-5")
                specification = st.text_input("规格", placeholder="如：500ml")
                unit = st.selectbox("单位", ["g", "ml", "L", "kg", "瓶", "支"])
            with col_b:
                quantity = st.number_input("数量 *", min_value=0.0, value=100.0, step=10.0)
                storage_location = st.text_input("存储位置", placeholder="如：A-01")
                is_controlled = st.checkbox("管控试剂")
                st.markdown("&nbsp;")
                st.markdown("&nbsp;")

            submitted = st.form_submit_button("提交入库", type="primary", use_container_width=True)

            if submitted:
                if not reagent_name.strip():
                    st.error("试剂名称不能为空")
                else:
                    next_bn = get_next_bottle_number()
                    ok = add_bottle(
                        bottle_number=next_bn,
                        reagent_name=reagent_name.strip(),
                        cas_number=cas_number.strip(),
                        specification=specification.strip(),
                        quantity=quantity,
                        unit=unit,
                        storage_location=storage_location.strip(),
                        creator_id=current_user.user_id,
                        creator_name=current_user.display_name,
                        is_controlled=is_controlled,
                    )
                    if ok:
                        st.success(f"试剂已入库！瓶号: {next_bn}")
                        st.rerun()
                    else:
                        st.error("入库失败，请检查数据")

        st.divider()
        st.markdown("##### 我录入的试剂瓶")
        my_bottles = get_bottles_by_creator(current_user.user_id)
        if my_bottles:
            my_data = [{
                "瓶号": b.bottle_number,
                "试剂名称": b.reagent_name,
                "CAS号": b.cas_number or "-",
                "规格": b.specification,
                "剩余量": f"{b.quantity} {b.unit}",
                "存储位置": b.storage_location,
            } for b in my_bottles]
            st.dataframe(my_data, use_container_width=True, hide_index=True)
        else:
            st.caption("暂无录入记录")

# ══════════════════════════════════════════════════════════
# Tab 5: 用户管理
# ══════════════════════════════════════════════════════════

if can_manage_users(current_role)[0]:
    tab_idx = tab_names.index("👥 用户管理")
    with tabs[tab_idx]:
        st.subheader("👥 用户管理")

        all_users = get_all_users()
        user_data = [{
            "用户ID": u.user_id,
            "名称": u.name,
            "工号": u.work_id,
            "角色": get_role_label(u.role),
            "部门": u.department,
            "创建时间": u.created_at,
        } for u in all_users]
        st.dataframe(user_data, use_container_width=True, hide_index=True)

        st.divider()
        col_x, col_y = st.columns(2)

        with col_x:
            st.markdown("##### 添加新用户")
            with st.form("add_user_form"):
                new_uid = st.text_input("用户ID *", placeholder="如: ST003")
                new_name = st.text_input("用户名称 *", placeholder="显示用")
                new_work = st.text_input("工号 *", placeholder="登录用")
                new_pwd = st.text_input("密码", value="123456", type="password")
                new_role = st.selectbox(
                    "角色",
                    options=["super_admin", "admin", "teacher", "student"],
                    format_func=lambda x: get_role_label(x),
                )
                new_dept = st.text_input("部门", placeholder="所属部门")

                if st.form_submit_button("添加用户", type="primary", use_container_width=True):
                    if not new_uid.strip() or not new_name.strip() or not new_work.strip():
                        st.error("用户ID、名称、工号为必填项")
                    else:
                        ok = add_user(
                            user_id=new_uid.strip(),
                            name=new_name.strip(),
                            work_id=new_work.strip(),
                            password=new_pwd.strip() or "123456",
                            role=new_role,
                            department=new_dept.strip(),
                        )
                        if ok:
                            st.success(f"用户 {new_name} 已添加")
                            st.rerun()
                        else:
                            st.error("添加失败，用户ID或工号可能已存在")

        with col_y:
            st.markdown("##### 设置从属管理员")
            st.caption("指定某用户从属于哪个管理员管辖")

            non_admin_users = [u for u in all_users if u.role not in ("super_admin", "admin")]
            admin_users = [u for u in all_users if u.role == "admin"]

            if non_admin_users and admin_users:
                with st.form("admin_relation_form"):
                    target_user = st.selectbox(
                        "选择用户（学生/教师）",
                        options=non_admin_users,
                        format_func=get_user_label,
                        key="rel_user",
                    )
                    target_admin = st.selectbox(
                        "选择管理员",
                        options=admin_users,
                        format_func=get_user_label,
                        key="rel_admin",
                    )
                    action = st.selectbox("操作", ["添加关联", "移除关联"])

                    if st.form_submit_button("执行", use_container_width=True):
                        uid = target_user.user_id
                        aid = target_admin.user_id
                        if action == "添加关联":
                            if add_user_admin_relation(uid, aid):
                                st.success(f"已将 {target_user.name} 关联到管理员 {target_admin.name}")
                                st.rerun()
                        else:
                            if remove_user_admin_relation(uid, aid):
                                st.success(f"已移除 {target_user.name} 与管理员 {target_admin.name} 的关联")
                                st.rerun()
            else:
                st.info("需要有学生/教师和管理员用户才能设置关联")

# ══════════════════════════════════════════════════════════
# Tab 6: 系统设置
# ══════════════════════════════════════════════════════════

if can_system_settings(current_role)[0]:
    tab_idx = tab_names.index("⚙️ 系统设置")
    with tabs[tab_idx]:
        st.subheader("⚙️ 系统设置")

        st.markdown("##### 系统信息")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("用户总数", len(get_all_users()))
        with col_b:
            st.metric("试剂瓶总数", len(get_all_bottles()))
        with col_c:
            st.metric("借出记录数", len(get_all_borrow_records()))

        st.divider()
        st.markdown("##### 数据库管理")

        if st.button("🔄 重置种子数据", use_container_width=True):
            db_path = os.path.join(os.path.dirname(__file__), "permission_demo.db")
            if os.path.exists(db_path):
                os.remove(db_path)
            init_db()
            seed_data()
            st.success("数据库已重置")
            st.rerun()

        st.divider()
        st.markdown("##### 角色说明")

        role_descriptions = {
            "🔴 超级管理员": "仅负责系统数据维护：用户管理、系统设置、试剂编辑/删除（数据维护）。无借出和审批权限。",
            "🟠 管理员": "管理自己录入的试剂瓶（新增/编辑/删除），可借出试剂，可审批自己试剂瓶的借出申请。",
            "🟢 教师": "可查看全部试剂，可借出任一试剂瓶（需试剂瓶所属管理员审批）。",
            "🔵 学生": "默认未登录即学生权限，仅可查看试剂，不可借出/编辑/删除。",
        }

        for title, desc in role_descriptions.items():
            st.markdown(f"**{title}**")
            st.markdown(f"> {desc}")

# ── 页脚 ────────────────────────────────────────────────

st.divider()
st.caption("权限系统演示 v2.0 | 四层分级: 超级管理员(系统维护) > 管理员(瓶管理+审批) > 教师(借出) > 学生(仅查看)")