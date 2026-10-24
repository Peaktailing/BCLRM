"""实时库存页面

显示当前试剂库存状态，支持快速查看和筛选。
"""
import io
import re
import zipfile

import streamlit as st
from business.inventory_service import inventory_service
from business.query_service import query_service
from business.manager_service import manager_service
from business.bottle_state import is_borrowable_now
from components.sidebar_nav import render_sidebar
from components.auth import require_auth
from services.base.system_config_service import EvidenceConfig, system_config_service
from services.core.reagent_bottle_service import reagent_bottle_service
from utils.qr_label import NAME_MAX_CHARS, label_fit, label_png, payload_of

def _derive_bottle_status(bottle):
    """从 borrowable_check 和其他字段派生显示状态"""
    if getattr(bottle, 'expired_flag', None) == '已过期':
        return '已过期'
    if not getattr(bottle, 'borrowable_check', True):
        if getattr(bottle, 'remaining_quantity', 0) == 0:
            return '耗尽'
        return '已借出'
    return '可借'


def main():
    """主函数：实时库存页面"""
    st.set_page_config(page_title="实时库存", layout="wide")
    st.title("📦 实时库存")
    
    # 认证检查
    if not require_auth():
        st.stop()
    
    # 使用统一的侧边栏导航
    render_sidebar()
    
    # 获取所有试剂
    result = query_service.get_all_reagents()
    reagents = result.data if result.is_success() else []
    
    # 统计信息（可借口径与查询层 is_borrowable_now 二次过滤对齐：
    # 已过期 / 已报废 / 无量的瓶不计入可借）
    total_count = len(reagents)
    borrowable_count = sum(1 for r in reagents if is_borrowable_now(r))
    exhausted_count = sum(
        1 for r in reagents
        if getattr(r, 'expired_flag', None) != '已过期'
        and not getattr(r, 'scrap_flag', None)
        and not is_borrowable_now(r)
        and getattr(r, 'remaining_quantity', 0) == 0
    )
    expired_count = sum(1 for r in reagents if getattr(r, 'expired_flag', None) == '已过期')
    
    # 统计卡片
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("试剂瓶总数", total_count)
    with col2:
        st.metric("可借数量", borrowable_count)
    with col3:
        st.metric("已耗尽", exhausted_count)
    with col4:
        st.metric("已过期", expired_count)
    
    st.divider()
    
    # ---------- 条码查询（扫码枪 / 手动输入） ----------
    with st.expander("🔎 条码查询（扫码枪扫码后自动查询）", expanded=False):
        _barcode = st.text_input(
            "试剂瓶条码",
            placeholder="用扫码枪扫描条码，或手动输入后回车",
            key="barcode_query_input",
        )
        if _barcode and _barcode.strip():
            _bc_result = inventory_service.retrieve_inventory_by_barcode(_barcode.strip())
            if _bc_result.is_success() and _bc_result.data:
                _b = _bc_result.data
                st.success(f"✅ 找到试剂瓶：{_b.bottle_number}｜{_b.reagent_name or '-'}")
                st.dataframe(
                    [{
                        "编号": _b.bottle_number,
                        "名称": _b.reagent_name or "-",
                        "CAS号": _b.cas_number or "-",
                        "条码": _b.barcode or "-",
                        "剩余量": _b.remaining_quantity,
                        "规格": _b.specification or "-",
                        "状态": _b.borrowable_flag or "-",
                        "过期状态": _b.expired_flag or "正常",
                        "存储位置": _b.storage_location or "-",
                        "管理人": manager_service.resolve_manager(getattr(_b, "manager", None)) or "—",
                    }],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.warning("未找到该条码对应的试剂瓶")

    # ---------- 瓶身二维码标签 ----------
    #
    # 手机办借还最难的一步是「说出是哪一瓶」：手输 202610230001 在 4 寸屏
    # 上是二十几次点击。贴个码，扫一下就进。
    #
    # 码里放什么由「手机访问地址」决定：配了就是一条 URL（手机相机直接扫就
    # 能打开），没配就是短码 BCLRM:3:（瓶号 + CAS + 效期 + 试剂名，得用手机
    # 取证页里的摄像头扫）。短码多背的那几段是给「系统不在」的时候用的。
    with st.expander("🖨️ 打印瓶身二维码标签", expanded=False):
        _base_url = system_config_service.get(EvidenceConfig.MOBILE_BASE_URL, "")
        if _base_url:
            st.caption(f"二维码将指向：`{_base_url.rstrip('/')}/m?bottle=<瓶号>`")
        else:
            st.caption(
                "还没配「手机访问地址」，二维码里放的是短码 "
                "`BCLRM:3:<瓶号>;<CAS>;<效期>;<名>`。"
                "想让手机相机直接扫开，请到「系统设置 → 现场取证」里填上地址。"
            )
        _label_input = st.text_area(
            "要打印的瓶号（每行一个，也可用逗号分隔）",
            key="qr_label_input",
            placeholder="202610230001\n202610230002",
            height=100,
        )
        _numbers = [
            item
            for item in re.split(r"[,，;；\s]+", _label_input or "")
            if item.strip()
        ]
        # 打印前先把「装得下吗」这笔账算出来。码里放 URL 时，地址越长码越密，
        # 密到一定程度小瓶标签上就扫不动了——这件事必须在贴上去之前知道，
        # 而不是打完一沓标签、贴到瓶上才发现扫不出。
        _probe_number = _numbers[0] if _numbers else "202610230001"
        # 探测也得用真实的 CAS、效期与试剂名：这三个字段让码从 21 字节涨到
        # 100 字节以上，用空值探测会算小两三个版本，报账就白报了。
        _probe = (
            reagent_bottle_service.get_by_bottle_number(_probe_number)
            if _numbers
            else None
        )
        if _probe is not None:
            _probe_payload = payload_of(
                _probe_number,
                _base_url,
                getattr(_probe, "cas_number", "") or "",
                getattr(_probe, "expiry_date", "") or "",
                getattr(_probe, "reagent_name", "") or "",
            )
        else:
            # 库里的瓶查不到（或还没输入瓶号）时按最长形态估：宁可报密，
            # 不可报松——名字按 NAME_MAX_CHARS 个汉字顶格填。
            _probe_payload = payload_of(
                _probe_number,
                _base_url,
                "0000000-00-0",
                "2027-06-30",
                "试" * NAME_MAX_CHARS,
            )
        # 用 label_fit 而不是 fit：fit 算的是名义尺寸，实际出图按整数倍模块
        # 取整后会小一两毫米，判级能差一档（名义 good、打出来 tight）。
        _fit = label_fit(_probe_payload)
        if _fit:
            st.caption(
                ("预估：" if _probe is None else "")
                + f"码内容 {_fit.payload_bytes} 字节 → 版本 {_fit.version}"
                f"（{_fit.modules} 模块），码在标签上占 {_fit.print_mm:.1f} mm、"
                f"每模块 {_fit.module_mm:.2f} mm"
            )
            st.caption(
                f"短码格式：`BCLRM:3:<瓶号>;<CAS>;<效期>;<名>`。"
                f"试剂名最多放 {NAME_MAX_CHARS} 个汉字，超了自动截断"
                "（优先保留括号里的缩写，如 DTNB）。"
            )
            if _fit.grade == "tight":
                st.warning(
                    "模块偏小，手机得凑近才扫得稳。缩短「手机访问地址」"
                    "（用主机名代替长 IP），或把标签放大到 1.3 倍以上再打。"
                )
            elif _fit.grade == "too_small":
                st.error(
                    "这个尺寸下基本扫不出来。请缩短手机访问地址，"
                    "或按原尺寸 1.5 倍以上放大打印。"
                )
        if _numbers:
            if st.button(f"生成 {len(_numbers)} 张标签", key="qr_label_build"):
                _labels = {}
                _missing = []
                for _number in _numbers:
                    _bottle = reagent_bottle_service.get_by_bottle_number(_number)
                    if _bottle is None:
                        _missing.append(_number)
                        continue
                    _cas = getattr(_bottle, "cas_number", "") or ""
                    _expiry = getattr(_bottle, "expiry_date", "") or ""
                    _name = getattr(_bottle, "reagent_name", "") or ""
                    _png = label_png(
                        _number,
                        name=_name,
                        payload=payload_of(_number, _base_url, _cas, _expiry, _name),
                        cas=_cas,
                        expiry=_expiry,
                    )
                    if _png:
                        _labels[_number] = _png
                if _missing:
                    st.warning("这些瓶号在库存里找不到：" + "、".join(_missing))
                if _labels:
                    st.session_state["qr_labels"] = _labels
                else:
                    st.error("一张都没生成出来。请检查瓶号，或确认已安装 segno。")

        _labels = st.session_state.get("qr_labels") or {}
        if _labels:
            _cols = st.columns(3)
            for _index, (_number, _png) in enumerate(_labels.items()):
                with _cols[_index % 3]:
                    st.image(_png, use_container_width=True)
                    st.download_button(
                        "下载",
                        data=_png,
                        file_name=f"label_{_number}.png",
                        mime="image/png",
                        key=f"qr_dl_{_number}_{_index}",
                    )
            # 一次打一批标签是常态（新入库几十瓶），逐个下载不现实
            _buffer = io.BytesIO()
            with zipfile.ZipFile(_buffer, "w", zipfile.ZIP_DEFLATED) as _zip:
                for _number, _png in _labels.items():
                    _zip.writestr(f"label_{_number}.png", _png)
            st.download_button(
                f"打包下载全部（{len(_labels)} 张）",
                data=_buffer.getvalue(),
                file_name="bottle_labels.zip",
                mime="application/zip",
                type="primary",
                key="qr_dl_zip",
            )

    # 管理权流转已移至「试剂处置」页面（支持多选 / 批量流转）

    # 获取所有试剂名称用于模糊匹配
    reagent_names = sorted(set(r.reagent_name for r in reagents if r.reagent_name))
    
    # 搜索筛选 - 支持模糊匹配候选项
    selected_name = st.selectbox(
        "搜索试剂名称（模糊匹配）",
        options=[""] + reagent_names,
        index=0,
        help="输入关键词可模糊匹配试剂名称"
    )
    
    # 状态筛选（已过期在业务层按 expired_flag 派生过滤）
    status_filter = st.selectbox("状态筛选", ["全部", "可借", "已借出", "耗尽", "已过期"])
    
    # 额外的文本搜索（支持CAS号、编号等）
    extra_search = st.text_input("额外搜索（CAS号/编号）")
    
    # 使用业务层统一过滤方法
    status_param = None if status_filter == "全部" else status_filter
    _filter_result = query_service.filter_reagents(
        keyword=extra_search if extra_search else None,
        reagent_name=selected_name if selected_name else None,
        status=status_param,
        borrowable_only=False,
    )
    filtered_reagents = _filter_result.data if _filter_result.is_success() else []
    
    # 显示试剂列表
    if filtered_reagents:
        # 准备表格数据
        table_data = []
        for reagent in filtered_reagents:
            status = _derive_bottle_status(reagent)
            status_color = {
                "可借": "🟢",
                "已借出": "🔵",
                "耗尽": "🔴",
                "已过期": "⚫"
            }.get(status, "⚪")
            
            table_data.append({
                "编号": reagent.bottle_number,
                "名称": reagent.reagent_name or "-",
                "CAS号": reagent.cas_number or "-",
                "剩余量": (
                    f"{reagent.remaining_quantity}{getattr(reagent, 'unit', None) or 'g'}"
                    if reagent.remaining_quantity else "-"
                ),
                "规格": (
                    f"{reagent.specification}{getattr(reagent, 'unit', None) or 'g'}"
                    if reagent.specification else "-"
                ),
                "纯度": reagent.purity or "-",
                "启封日期": reagent.unseal_date or "-",
                "过期状态": reagent.expired_flag or "正常",
                "状态": f"{status_color} {status}",
                "存储位置": reagent.storage_location or "-",
                "管理人": manager_service.resolve_manager(getattr(reagent, "manager", None)) or "—"
            })
        
        # 显示表格
        st.dataframe(table_data, use_container_width=True, hide_index=True)
    else:
        st.info("没有找到匹配的试剂")

if __name__ == "__main__":
    main()