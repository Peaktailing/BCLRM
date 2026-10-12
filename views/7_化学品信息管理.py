"""化学品信息管理页面

化学品信息管理的UI页面，仅负责展示和用户交互，不包含任何业务逻辑。
所有业务逻辑调用 business/chemical_service.py 中的函数。
"""
import streamlit as st
from business.chemical_service import chemical_manage_service
from components.sidebar_nav import render_sidebar
from components.auth import require_auth
from utils.attachment_store import attachment_store
from utils.formula_utils import format_formula
from utils.error_handler import logger

MSDS_FILE_TYPES = ["jpg", "jpeg", "png", "pdf", "doc", "docx", "txt"]
MSDS_MAX_SIZE_MB = 10

# 系统兜底默认值
FALLBACK_UNSEALED = 730
FALLBACK_SEALED = 365


def _store_msds(uploaded_file, ref_id=None):
    """保存 MSDS 附件到附件库（物理文件 + 索引）

    Args:
        uploaded_file: Streamlit 上传的文件对象，None 返回 None
        ref_id: 关联的化学品名称（用于附件索引）

    Returns:
        存储文件名（写入 chemical_info.msds 字段），无文件返回 None。
        校验失败时显示错误并中止本次提交（st.stop）。
    """
    if uploaded_file is None:
        return None
    try:
        return attachment_store.save(
            uploaded_file,
            category="msds",
            allowed_exts=MSDS_FILE_TYPES,
            max_mb=MSDS_MAX_SIZE_MB,
            ref_type="chemical",
            ref_id=ref_id,
        )
    except ValueError as e:
        st.error(f"MSDS附件保存失败：{e}")
        st.stop()
        return None  # st.stop 正常情况下不会到达；显式返回避免静态检查告警与裸环境 fall-through


def _clean_msds(msds_value):
    """规范化 MSDS 字段值

    历史数据存在三类脏值：字符串 'nan'（批量导入污染）、None、空串，
    统一归一为 None；旧系统 URL 格式（含 /api/attachments/）原样保留以便识别。

    Args:
        msds_value: chemical_info.msds 原始值

    Returns:
        可用的存储文件名 / 旧系统附件串，或 None
    """
    if msds_value is None:
        return None
    value = str(msds_value).strip()
    if not value or value.lower() == "nan":
        return None
    return value


def _download_msds(msds_value):
    """渲染当前 MSDS 附件的下载入口

    Args:
        msds_value: chemical_info.msds 存储值（存储文件名 / 旧系统附件串 / 历史脏值）
    """
    value = _clean_msds(msds_value)
    if not value:
        return
    # 历史旧系统附件（CodeBuddy 导入的 URL 格式），文件不在本地附件目录
    if "/api/attachments/" in value:
        legacy_name = value.split(" /")[0].strip()
        st.caption(f"MSDS：{legacy_name}（历史旧系统附件，文件未迁移到本地，如需查看请重新上传）")
        return
    content = attachment_store.load(value)
    if content is None:
        st.caption(f"MSDS：{value}（历史文件缺失）")
        return
    display_name = attachment_store.original_name(value) or value
    st.download_button(
        f"📥 下载 MSDS（{display_name}）",
        data=content,
        file_name=display_name,
        use_container_width=True,
        key=f"dl_msds_{value}",
    )


def _compute_default_shelf_life(type_names_list):
    """根据试剂类型列表计算默认有效期（取最短值）"""
    if not type_names_list:
        return FALLBACK_UNSEALED, FALLBACK_SEALED
    _r = chemical_manage_service.get_default_shelf_life_by_types(type_names_list)
    if _r.is_success() and _r.data:
        return _r.data.get("unsealed", FALLBACK_UNSEALED), _r.data.get("sealed", FALLBACK_SEALED)
    return FALLBACK_UNSEALED, FALLBACK_SEALED


def _parse_reagent_type_str(type_str):
    """将逗号分隔的试剂类型字符串解析为列表"""
    if not type_str:
        return []
    return [t.strip() for t in type_str.split(",") if t.strip()]


def _chem_label(chemical) -> str:
    """化学品下拉标签：显示「名称（通用显示名称）」

    避免只有 name 可见时，找不到「氯化氢水溶液（盐酸）」这类记录。
    """
    name = getattr(chemical, 'name', '') or ''
    display = getattr(chemical, 'display_name', '') or ''
    if display and display != name:
        return f"{name}（{display}）"
    return name


def main():
    st.set_page_config(page_title="化学品信息管理", layout="wide")
    st.title("🧪 化学品信息管理")

    # 认证检查
    if not require_auth():
        st.stop()

    # 使用统一的侧边栏导航
    render_sidebar()

    # ========== 顶部：化学品列表 ==========
    st.subheader("📋 化学品列表")

    search_query = st.text_input("搜索化学品（名称/显示名称）", placeholder="输入关键词进行模糊搜索...")

    chemicals = []
    try:
        _result = chemical_manage_service.get_all_chemicals()
        chemicals = _result.data if _result.is_success() else []
    except Exception as e:
        logger.error(f"加载化学品列表失败: {str(e)}", exception=e)
        st.error("无法加载化学品列表，请检查数据库连接。")
        st.info("可能的原因：1. 数据库服务不可用 2. 表结构未初始化")

    if search_query and chemicals:
        try:
            _result = chemical_manage_service.search_chemicals(search_query)
            filtered_chemicals = _result.data if _result.is_success() else []
        except Exception as e:
            logger.error(f"搜索化学品失败: {str(e)}", exception=e)
            st.error("搜索失败，请稍后重试。")
            filtered_chemicals = chemicals
    else:
        filtered_chemicals = chemicals

    if filtered_chemicals:
        table_data = []
        for chemical in filtered_chemicals:
            controlled_badge = "🔴" if getattr(chemical, 'controlled_type', None) else "⚪"
            unsealed = getattr(chemical, 'unsealed_shelf_life', None)
            sealed = getattr(chemical, 'sealed_shelf_life', None)
            table_data.append({
                "化学品名称": getattr(chemical, 'name', '-'),
                "通用显示名称": getattr(chemical, 'display_name', '-'),
                "化学式": format_formula(getattr(chemical, 'formula', '-')),
                "CAS号": getattr(chemical, 'cas_number', '-'),
                "试剂类型": getattr(chemical, 'reagent_type', '-'),
                "存储要求": getattr(chemical, 'storage_requirement', '-'),
                "管控类型": f"{controlled_badge} {getattr(chemical, 'controlled_type', '')}" if getattr(chemical, 'controlled_type', None) else "无",
                "未启封有效期（天）": f"{unsealed}天" if unsealed else "默认",
                "启封有效期（天）": f"{sealed}天" if sealed else "默认",
                "MSDS": "✅" if getattr(chemical, 'msds', None) else "❌"
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)
    else:
        st.info("没有找到匹配的化学品")

    # ========== 中部：添加新化学品表单 ==========
    st.divider()
    st.subheader("➕ 添加新化学品")

    # 试剂类型多选框（从业务层获取）
    _result = chemical_manage_service.get_reagent_type_names()
    reagent_type_names = _result.data if _result.is_success() else []

    if not reagent_type_names:
        st.warning("试剂类型数据加载失败，请检查数据库连接")

    # 试剂类型多选（表单外，选择后即时刷新默认有效期）
    selected_types_add = st.multiselect(
        "试剂类型*（可多选）",
        options=reagent_type_names,
        help="选择一个或多个试剂类型，有效期默认值取所选类型中最短的",
        key="add_selected_types"
    )

    # 根据所选试剂类型计算默认有效期
    default_unsealed_add, default_sealed_add = _compute_default_shelf_life(selected_types_add)

    # 存储要求下拉框（从业务层获取）
    _result = chemical_manage_service.get_storage_requirement_names()
    storage_requirement_names = _result.data if _result.is_success() else []
    if not storage_requirement_names:
        st.warning("存储要求数据加载失败，请检查数据库连接")
        storage_requirement = st.text_input("存储要求*", help="手动输入存储要求")
    else:
        storage_requirement = st.selectbox(
            "存储要求*",
            options=storage_requirement_names,
            help="从存储要求表中选择"
        )

    # 构建化学品名称下拉选项（用于添加表单，标签含通用显示名称）
    chemical_options_dict = {_chem_label(c): c for c in chemicals if getattr(c, 'name', '')}
    chemical_names_for_select = [""] + list(chemical_options_dict.keys())

    with st.form("add_chemical_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_chemical_name = st.selectbox(
                "化学品名称*（下拉选择或输入新名称）",
                options=chemical_names_for_select,
                index=0,
                help="从已有化学品中选择（格式：名称（通用显示名称））；或直接输入新名称后按回车",
                accept_new_options=True,
            )

            if selected_chemical_name and selected_chemical_name in chemical_options_dict:
                selected = chemical_options_dict[selected_chemical_name]
                name = st.text_input("化学品名称*", value=getattr(selected, 'name', ''))
                cas = st.text_input("CAS号（只读）", value=getattr(selected, 'cas_number', ''), disabled=True)
                display_name = st.text_input("通用显示名称", value=getattr(selected, 'display_name', ''))
                formula = st.text_input("化学式", value=getattr(selected, 'formula', ''))
            else:
                name = st.text_input("化学品名称*（输入新名称）")
                cas = st.text_input("CAS号*", help="化学品的CAS编号，纯文本格式")
                display_name = st.text_input("通用显示名称", help="化学品的通用显示名称")
                formula = st.text_input("化学式", help="化学品的分子式，纯文本格式")

        with col2:
            msds = st.file_uploader(
                "MSDS附件",
                type=MSDS_FILE_TYPES,
                help=f"支持格式：{', '.join(MSDS_FILE_TYPES)}，大小限制：{MSDS_MAX_SIZE_MB}MB"
            )
            unsealed_life = st.number_input(
                "未启封有效期（天）",
                min_value=0,
                value=default_unsealed_add,
                help=f"试剂未启封时的有效期（天），已根据试剂类型自动填充（最短值），可手动修改。0表示永久有效"
            )
            sealed_life = st.number_input(
                "启封有效期（天）",
                min_value=0,
                value=default_sealed_add,
                help=f"试剂启封后的有效期（天），已根据试剂类型自动填充（最短值），可手动修改。0表示启封后永久有效"
            )

        submitted = st.form_submit_button("添加化学品", type="primary", use_container_width=True)

        if submitted:
            if not selected_types_add:
                st.error("请至少选择一个试剂类型")
            else:
                reagent_type_str = ", ".join(selected_types_add)
                msds_value = _store_msds(msds, ref_id=name)
                _result = chemical_manage_service.create_chemical(
                    name=name,
                    display_name=display_name,
                    formula=formula,
                    cas=cas,
                    msds=msds_value,
                    reagent_type=reagent_type_str,
                    storage_requirement=storage_requirement,
                    unsealed_shelf_life=unsealed_life if unsealed_life > 0 else None,
                    sealed_shelf_life=sealed_life if sealed_life > 0 else None,
                )

                if _result.is_success():
                    st.success(_result.message)
                    st.rerun()
                else:
                    st.error(_result.message)

    # ========== 底部：编辑化学品区域 ==========
    st.divider()
    st.subheader("✏️ 编辑化学品")

    try:
        _result = chemical_manage_service.get_all_chemicals()
        chemicals_for_edit = _result.data if _result.is_success() else []
    except Exception as e:
        chemicals_for_edit = []
        logger.error(f"获取化学品列表失败: {str(e)}", exception=e)
        st.error("获取化学品列表失败，请检查数据库连接。")

    if chemicals_for_edit:
        # 标签含通用显示名称，避免「氯化氢水溶液（盐酸）」这类记录找不到
        chemical_options = {
            _chem_label(c): c for c in chemicals_for_edit if getattr(c, 'name', '')
        }
        selected_chemical_to_edit = st.selectbox(
            "选择要编辑的化学品（格式：名称（通用显示名称））",
            options=[""] + list(chemical_options.keys()),
            index=0,
            key="edit_chemical_select_v2"
        )

        if selected_chemical_to_edit:
            selected_chemical = chemical_options[selected_chemical_to_edit]
            # 直接使用下拉选中的对象，避免按名称二次查询造成错位
            chem = selected_chemical

            # 当前 MSDS 附件下载入口（表单外，Streamlit 表单内不支持下载按钮）
            _download_msds(getattr(chem, 'msds', None))

            # 解析当前试剂类型为列表
            current_types = _parse_reagent_type_str(getattr(chem, 'reagent_type', '')) if chem else []

            # 试剂类型多选（表单外，选择后即时刷新默认有效期）
            selected_types_edit = st.multiselect(
                "试剂类型*（可多选）",
                options=reagent_type_names,
                default=[t for t in current_types if t in reagent_type_names],
                help="选择一个或多个试剂类型，有效期默认值取所选类型中最短的",
                key="edit_selected_types"
            )

            # 根据所选试剂类型计算默认有效期
            default_unsealed_edit, default_sealed_edit = _compute_default_shelf_life(selected_types_edit)

            # 切换化学品时重置有效期输入框（使用动态 key 强制重建 widget）
            chem_id = getattr(selected_chemical, 'id', 'new')
            if st.session_state.get("edit_current_chem_id") != chem_id:
                st.session_state["edit_current_chem_id"] = chem_id
                # 首次加载使用化学品已有值，否则使用试剂类型默认值
                current_unsealed = getattr(chem, 'unsealed_shelf_life', None) if chem else None
                current_sealed = getattr(chem, 'sealed_shelf_life', None) if chem else None
                st.session_state["edit_unsealed_default"] = current_unsealed if current_unsealed is not None else default_unsealed_edit
                st.session_state["edit_sealed_default"] = current_sealed if current_sealed is not None else default_sealed_edit
            # 试剂类型变化时更新默认值（写入独立的 session_state key，不与 widget key 冲突）
            elif st.session_state.get("edit_prev_types") != selected_types_edit:
                st.session_state["edit_unsealed_default"] = default_unsealed_edit
                st.session_state["edit_sealed_default"] = default_sealed_edit
            st.session_state["edit_prev_types"] = selected_types_edit

            # 自动选中对应的存储要求
            if chem and chem.storage_requirement in storage_requirement_names:
                default_storage_requirement = chem.storage_requirement
            else:
                default_storage_requirement = storage_requirement_names[0] if storage_requirement_names else ""

            with st.form("edit_chemical_form", clear_on_submit=False):
                col1, col2 = st.columns(2)

                with col1:
                    edit_name = st.text_input("化学品名称*", value=getattr(selected_chemical, 'name', ''))
                    edit_cas = st.text_input("CAS号*", value=getattr(selected_chemical, 'cas_number', ''))

                    # 存储要求下拉框 - 带默认值
                    if storage_requirement_names:
                        edit_storage_requirement = st.selectbox(
                            "存储要求*",
                            options=storage_requirement_names,
                            index=storage_requirement_names.index(default_storage_requirement) if default_storage_requirement else 0,
                            help="从存储要求表中选择"
                        )
                    else:
                        st.warning("存储要求数据加载失败")
                        edit_storage_requirement = st.text_input("存储要求*", value=getattr(selected_chemical, 'storage_requirement', ''))

                with col2:
                    edit_display_name = st.text_input("通用显示名称", value=getattr(selected_chemical, 'display_name', ''))
                    edit_formula = st.text_input("化学式", value=getattr(selected_chemical, 'formula', ''))
                    edit_unsealed_life = st.number_input(
                        "未启封有效期（天）",
                        min_value=0,
                        value=st.session_state.get("edit_unsealed_default", default_unsealed_edit),
                        key=f"edit_unsealed_life_{chem_id}",
                        help="试剂未启封时的有效期（天），已根据试剂类型自动填充（最短值），可手动修改"
                    )
                    edit_sealed_life = st.number_input(
                        "启封有效期（天）",
                        min_value=0,
                        value=st.session_state.get("edit_sealed_default", default_sealed_edit),
                        key=f"edit_sealed_life_{chem_id}",
                        help="试剂启封后的有效期（天），已根据试剂类型自动填充（最短值），可手动修改"
                    )
                    edit_msds = st.file_uploader(
                        "更新MSDS附件",
                        type=MSDS_FILE_TYPES,
                        help=f"支持格式：{', '.join(MSDS_FILE_TYPES)}，大小限制：{MSDS_MAX_SIZE_MB}MB"
                    )

                edit_submitted = st.form_submit_button("更新化学品", type="primary", use_container_width=True)

                if edit_submitted:
                    if not selected_types_edit:
                        st.error("请至少选择一个试剂类型")
                    else:
                        reagent_type_str = ", ".join(selected_types_edit)
                        if edit_msds:
                            # 上传新附件：真实存储，删除旧文件
                            edit_msds_value = _store_msds(
                                edit_msds,
                                ref_id=getattr(selected_chemical, 'name', ''),
                            )
                            _old_msds = _clean_msds(getattr(selected_chemical, 'msds', None))
                            if _old_msds and _old_msds != edit_msds_value:
                                attachment_store.delete(_old_msds)
                        else:
                            edit_msds_value = _clean_msds(getattr(selected_chemical, 'msds', None))
                        _result = chemical_manage_service.update_chemical(
                            record_id=getattr(selected_chemical, 'id', ''),
                            name=edit_name,
                            display_name=edit_display_name,
                            formula=edit_formula,
                            cas=edit_cas,
                            msds=edit_msds_value,
                            reagent_type=reagent_type_str,
                            storage_requirement=edit_storage_requirement,
                            unsealed_shelf_life=edit_unsealed_life if edit_unsealed_life > 0 else None,
                            sealed_shelf_life=edit_sealed_life if edit_sealed_life > 0 else None,
                        )

                        if _result.is_success():
                            st.success(_result.message)
                            st.rerun()
                        else:
                            st.error(_result.message)
    else:
        st.info("暂无化学品数据，无法进行编辑")

    # ========== 底部：试剂类型有效期配置 ==========
    st.divider()
    st.subheader("⚙️ 试剂类型有效期配置")
    st.caption("为每种试剂类型设置默认的未启封有效期和启封有效期（单位：天）。化学品录入时选择类型后会自动填充对应默认值。")

    _result = chemical_manage_service.get_all_reagent_types()
    all_reagent_types = _result.data if _result.is_success() else []

    if all_reagent_types:
        config_table_data = []
        for rt in all_reagent_types:
            config_table_data.append({
                "试剂类型": getattr(rt, 'name', '-'),
                "描述": getattr(rt, 'description', '-') or '-',
                "默认未启封有效期（天）": getattr(rt, 'default_unsealed_shelf_life', None) or "未设置",
                "默认启封有效期（天）": getattr(rt, 'default_sealed_shelf_life', None) or "未设置",
            })
        st.dataframe(config_table_data, use_container_width=True, hide_index=True)

        # 编辑区域
        st.markdown("**修改默认有效期：**")
        rt_name_to_edit = st.selectbox(
            "选择试剂类型",
            options=[getattr(rt, 'name', '') for rt in all_reagent_types if getattr(rt, 'name', '')],
            key="rt_config_select"
        )

        if rt_name_to_edit:
            # 找到选中的类型
            rt_obj = next((rt for rt in all_reagent_types if getattr(rt, 'name', '') == rt_name_to_edit), None)
            current_rt_unsealed = getattr(rt_obj, 'default_unsealed_shelf_life', None) if rt_obj else None
            current_rt_sealed = getattr(rt_obj, 'default_sealed_shelf_life', None) if rt_obj else None

            col_a, col_b = st.columns(2)
            with col_a:
                new_rt_unsealed = st.number_input(
                    "默认未启封有效期（天）",
                    min_value=0,
                    value=current_rt_unsealed if current_rt_unsealed is not None else FALLBACK_UNSEALED,
                    key="rt_config_unsealed",
                    help="该类型试剂未启封时的默认有效期（天），0表示永久有效"
                )
            with col_b:
                new_rt_sealed = st.number_input(
                    "默认启封有效期（天）",
                    min_value=0,
                    value=current_rt_sealed if current_rt_sealed is not None else FALLBACK_SEALED,
                    key="rt_config_sealed",
                    help="该类型试剂启封后的默认有效期（天），0表示启封后永久有效"
                )

            if st.button("保存默认有效期", type="primary", key="save_rt_config"):
                _result = chemical_manage_service.update_reagent_type_shelf_life(
                    type_name=rt_name_to_edit,
                    default_unsealed_shelf_life=new_rt_unsealed if new_rt_unsealed > 0 else None,
                    default_sealed_shelf_life=new_rt_sealed if new_rt_sealed > 0 else None,
                )
                if _result.is_success():
                    st.success(_result.message)
                    st.rerun()
                else:
                    st.error(_result.message)
    else:
        st.info("暂无试剂类型数据")

if __name__ == "__main__":
    main()
