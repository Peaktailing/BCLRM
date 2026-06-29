"""
四层分级权限系统 - Streamlit 演示应用

无需修改现有项目代码，完全独立的权限演示。
默认未登录状态 = 学生权限（仅查看）。
"""

import streamlit as st
import os
import sys

# 将当前目录加入 path 以便导入
sys.path.insert(0, os.path.dirname(__file__))

from models import init_db, seed_data, User, ReagentBottle, BorrowRecord
from data import (
    get_user, get_all_users, get_users_by_role,
    get_all_bottles, get_bottles_by_creator, get_bottle_by_number,
    add_bottle, update_bottle, delete_bottle,
    get_all_borrow_records, get_borrow_records_by_borrower,
    get_pending_borrows, create_borrow_record, approve_borrow,
    get_next_bottle_number, get_next_record_number,
    add_user, delete_user,
)
from core import (
    Role, get_role_level, get_role_label,
    can_view_reagents, can_add_reagent, can_edit_reagent, can_delete_reagent,
    can_borrow_reagent, can_approve_borrow, can_manage_users, can_system_settings,
    can_view_all_reagents, get_role_permissions, PERMISSION_DESCRIPTIONS, ROLE_LABELS_ZH,
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
        st.session_state.user = None  # 当前登录用户
    if "role" not in st.session_state:
        st.session_state.role = "student"  # 默认未登录 = 学生


init_session()


# ── 初始化数据库 ──────────────────────────────────────────

@st.cache_resource
def init_database():
    init_db()
    seed_data()
    return True


init_database()


# ── 辅助函数 ──────────────────────────────────────────────

def get_current_user() -> User | None:
    """获取当前登录用户对象"""
    return st.session_state.user


def get_current_role() -> str:
    """获取当前角色 key"""
    if st.session_state.user:
        return st.session_state.user.role
    return st.session_state.role


def is_logged_in() -> bool:
    return st.session_state.user is not None


def role_badge(role: str) -> str:
    """角色标签带颜色"""
    colors = {
        "super_admin": "🔴",
        "admin": "🟠",
        "teacher": "🟢",
        "student": "🔵",
    }
    return f"{colors.get(role, '⚪')} {get_role_label(role)}"


def check_and_show(result: tuple) -> bool:
    """检查权限并显示提示"""
    ok, msg = result
    if not ok:
        st.warning(f"⛔ {msg}")
    return ok


# ── 侧边栏 - 登录/用户信息 ────────────────────────────────

with st.sidebar:
    st.title("🧪 权限系统演示")
    st.caption("四层分级权限管理")

    st.divider()

    if is_logged_in():
        user = get_current_user()
        st.success(f"已登录")
        st.markdown(f"**用户:** {user.display_name}")
        st.markdown(f"**角色:** {role_badge(user.role)}")
        st.markdown(f"**部门:** {user.department}")

        if st.button("🚪 退出登录", use_container_width=True):
            st.session_state.user = None
            st.rerun()
    else:
        st.info("当前处于**未登录状态**（学生权限 - 仅查看）")

        with st.expander("🔑 登录", expanded=True):
            # 获取所有用户供选择
            all_users = get_all_users()
            user_options = {f"{u.display_name} ({get_role_label(u.role)})": u.name for u in all_users}

            selected_label = st.selectbox(
                "选择用户",
                options=list(user_options.keys()),
                key="login_select",
            )

            if st.button("登录", use_container_width=True, type="primary"):
                username = user_options[selected_label]
                user_obj = get_user(username)
                if user_obj:
                    st.session_state.user = user_obj
                    st.rerun()

    st.divider()
    st.caption("权限提示：未登录=学生权限")

# ── 主界面 ────────────────────────────────────────────────

# 顶部角色信息栏
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

# 根据角色显示不同的 Tab
tab_names = ["📦 试剂库存"]

# 所有角色都能看到库存

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

# ── Tab 1: 试剂库存 ───────────────────────────────────────

with tabs[0]:
    st.subheader("📦 试剂库存一览")

    bottles = get_all_bottles()

    if not bottles:
        st.info("暂无试剂数据")
    else:
        # 展示格式化的数据
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
                "录入人": b.creator,
                "类型": ctrl_mark,
            })

        st.dataframe(data_rows, use_container_width=True, hide_index=True)

    # 显示编辑/删除按钮（根据权限）
    if bottles:
        st.divider()
        st.markdown("##### 试剂操作")

        can_edit, edit_msg = can_edit_reagent(current_role, get_current_user().name if is_logged_in() else None, None)
        can_del, del_msg = can_delete_reagent(current_role, get_current_user().name if is_logged_in() else None, None)

        if can_edit or can_del:
            with st.form("reagent_action_form"):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    bottle_options = {f"#{b.bottle_number} - {b.reagent_name} (录入: {b.creator})": b.bottle_number for b in bottles}
                    selected_bottle = st.selectbox("选择试剂瓶", options=list(bottle_options.keys()), key="edit_select")
                    bottle_num = bottle_options[selected_bottle]
                with col_b:
                    action_type = st.selectbox("操作类型", ["编辑", "删除"])

                if st.form_submit_button("执行", use_container_width=True):
                    bottle = get_bottle_by_number(bottle_num)
                    if not bottle:
                        st.error("未找到该试剂瓶")
                    elif action_type == "编辑":
                        ok, msg = can_edit_reagent(current_role, get_current_user().name if is_logged_in() else None, bottle.creator)
                        if ok:
                            st.info(f"演示模式：已准备编辑试剂 #{bottle_num}（{bottle.reagent_name}）")
                            st.success(msg)
                            # 在实际中这里会弹出编辑表单
                        else:
                            st.warning(f"⛔ {msg}")
                    elif action_type == "删除":
                        ok, msg = can_delete_reagent(current_role, get_current_user().name if is_logged_in() else None, bottle.creator)
                        if ok:
                            if delete_bottle(bottle_num):
                                st.success(f"试剂 #{bottle_num} 已删除")
                                st.rerun()
                            else:
                                st.error("删除失败")
                        else:
                            st.warning(f"⛔ {msg}")
        else:
            st.caption("当前角色无编辑/删除试剂权限")

# ── Tab 2: 借出试剂 ───────────────────────────────────────

if can_borrow_reagent(current_role)[0]:
    tab_idx = tab_names.index("📤 借出试剂")
    with tabs[tab_idx]:
        st.subheader("📤 借出试剂")

        if not is_logged_in():
            st.warning("请先登录后再借出试剂")
        else:
            col_a, col_b = st.columns([1, 1])

            with col_a:
                st.markdown("##### 发起借出申请")
                available_bottles = [b for b in get_all_bottles() if b.quantity > 0]

                with st.form("borrow_form"):
                    bottle_opts = {f"#{b.bottle_number} - {b.reagent_name} (余量: {b.quantity}{b.unit})": b for b in available_bottles}
                    selected = st.selectbox("选择试剂", options=list(bottle_opts.keys()), key="borrow_select")
                    bottle = bottle_opts[selected]

                    max_qty = bottle.quantity
                    qty = st.number_input(
                        f"借出数量（最大 {max_qty} {bottle.unit}）",
                        min_value=0.1, max_value=float(max_qty), value=min(10.0, float(max_qty)), step=0.1,
                    )

                    borrower_name = st.text_input("借用人", value=get_current_user().display_name)

                    submitted = st.form_submit_button("提交借出申请", type="primary", use_container_width=True)

                    if submitted:
                        if not borrower_name.strip():
                            st.error("请输入借用人姓名")
                        else:
                            record_number = get_next_record_number()
                            ok = create_borrow_record(
                                record_number=record_number,
                                bottle_number=bottle.bottle_number,
                                reagent_name=bottle.reagent_name,
                                borrower=borrower_name,
                                quantity=qty,
                            )
                            if ok:
                                st.success(f"借出申请已提交！记录编号：{record_number}")
                                st.info("等待教师或超级管理员审批...")
                                st.rerun()
                            else:
                                st.error("提交失败，请重试")

            with col_b:
                st.markdown("##### 我的借出记录")
                user_name = get_current_user().name
                my_records = get_borrow_records_by_borrower(get_current_user().display_name)
                if not my_records:
                    st.caption("暂无借出记录")
                else:
                    for r in my_records:
                        status_icon = {"待审批": "⏳", "已批准": "✅", "已拒绝": "❌"}.get(r.status, "❓")
                        st.markdown(
                            f"- {status_icon} **{r.reagent_name}** x{r.quantity} "
                            f"| {r.borrow_time} | **{r.status}**"
                            + (f" (审批人: {r.approver})" if r.approver else "")
                        )

# ── Tab 3: 审批管理 ─────────────────────────────────────

if can_approve_borrow(current_role)[0]:
    tab_idx = tab_names.index("✅ 审批管理")
    with tabs[tab_idx]:
        st.subheader("✅ 借出审批管理")

        pending = get_pending_borrows()
        if not pending:
            st.info("暂无待审批的借出申请")
        else:
            st.markdown(f"有 **{len(pending)}** 条待审批的借出申请")

            for record in pending:
                with st.container(border=True):
                    col_a, col_b, col_c = st.columns([3, 1, 1])
                    with col_a:
                        st.markdown(
                            f"**{record.reagent_name}** | "
                            f"借用人: {record.borrower} | "
                            f"数量: {record.quantity} | "
                            f"时间: {record.borrow_time}"
                        )
                    with col_b:
                        if st.button("✅ 批准", key=f"approve_{record.id}", use_container_width=True):
                            ok = approve_borrow(record.id, get_current_user().display_name, True)
                            if ok:
                                st.success("已批准")
                                st.rerun()
                    with col_c:
                        if st.button("❌ 拒绝", key=f"reject_{record.id}", use_container_width=True):
                            ok = approve_borrow(record.id, get_current_user().display_name, False)
                            if ok:
                                st.info("已拒绝")
                                st.rerun()

        st.divider()
        st.markdown("##### 所有审批记录")
        all_records = get_all_borrow_records()
        if all_records:
            record_data = []
            for r in all_records:
                record_data.append({
                    "记录编号": r.record_number,
                    "试剂": r.reagent_name,
                    "借用人": r.borrower,
                    "数量": r.quantity,
                    "借出时间": r.borrow_time,
                    "状态": r.status,
                    "审批人": r.approver or "-",
                })
            st.dataframe(record_data, use_container_width=True, hide_index=True)

# ── Tab 4: 试剂入库 ─────────────────────────────────────

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
                    creator = get_current_user().display_name if is_logged_in() else "未知"
                    ok = add_bottle(
                        bottle_number=next_bn,
                        reagent_name=reagent_name.strip(),
                        cas_number=cas_number.strip(),
                        specification=specification.strip(),
                        quantity=quantity,
                        unit=unit,
                        storage_location=storage_location.strip(),
                        creator=creator,
                        is_controlled=is_controlled,
                    )
                    if ok:
                        st.success(f"试剂已入库！瓶号: {next_bn}")
                        st.rerun()
                    else:
                        st.error("入库失败，请检查数据")

        st.divider()
        st.markdown("##### 我录入的试剂瓶")
        user_name = get_current_user().display_name if is_logged_in() else ""
        my_bottles = get_bottles_by_creator(user_name) if user_name else []
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

# ── Tab 5: 用户管理 ─────────────────────────────────────

if can_manage_users(current_role)[0]:
    tab_idx = tab_names.index("👥 用户管理")
    with tabs[tab_idx]:
        st.subheader("👥 用户管理")

        all_users = get_all_users()
        user_data = [{
            "ID": u.id,
            "用户名": u.name,
            "显示名": u.display_name,
            "角色": get_role_label(u.role),
            "部门": u.department,
            "创建时间": u.created_at,
        } for u in all_users]
        st.dataframe(user_data, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("##### 添加新用户")
        with st.form("add_user_form"):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                new_name = st.text_input("用户名 *", placeholder="登录用")
            with col_b:
                new_display = st.text_input("显示名称", placeholder="显示用")
            with col_c:
                new_role = st.selectbox("角色", options=["super_admin", "admin", "teacher", "student"],
                                        format_func=lambda x: get_role_label(x))
            new_dept = st.text_input("部门", placeholder="所属部门")

            if st.form_submit_button("添加用户", type="primary", use_container_width=True):
                if not new_name.strip():
                    st.error("用户名不能为空")
                else:
                    ok = add_user(
                        name=new_name.strip(),
                        role=new_role,
                        display_name=new_display.strip() or new_name.strip(),
                        department=new_dept.strip(),
                    )
                    if ok:
                        st.success(f"用户 {new_name} 已添加")
                        st.rerun()
                    else:
                        st.error("添加失败，用户名可能已存在")

# ── Tab 6: 系统设置 ─────────────────────────────────────

if can_system_settings(current_role)[0]:
    tab_idx = tab_names.index("⚙️ 系统设置")
    with tabs[tab_idx]:
        st.subheader("⚙️ 系统设置")

        st.markdown("##### 系统信息")
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("用户总数", len(get_all_users()))
        with col_b:
            st.metric("试剂瓶总数", len(get_all_bottles()))

        st.divider()
        st.markdown("##### 数据库管理")

        if st.button("🔄 重置种子数据", use_container_width=True):
            # 重新初始化数据库
            import os
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
            "🔴 超级管理员": "拥有系统所有信息更改权限，包括用户管理、系统设置、试剂CRUD、审批等全部功能。",
            "🟠 管理员": "可管理自己录入的试剂瓶（新增/编辑/删除），可借出试剂，不可审批。",
            "🟢 教师": "可查看全部试剂，可借出试剂，可审批借出申请。",
            "🔵 学生": "默认未登录即学生权限，仅可查看试剂，不可借出/编辑/删除。",
        }

        for title, desc in role_descriptions.items():
            st.markdown(f"**{title}**")
            st.markdown(f"> {desc}")

# ── 页脚 ────────────────────────────────────────────────

st.divider()
st.caption("权限系统演示 v1.0 | 四层分级: 超级管理员 > 管理员 > 教师 > 学生")