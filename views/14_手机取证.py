"""手机取证页：扫瓶身二维码 → 看这瓶是谁的、哪张单 → 拍照补证。

手机在实验室里的用法和电脑完全不同：人站在货架前，一只手拿瓶子。所以这一
页只有一个任务——**从「这一瓶」出发，找到它现在的那张单，把这次交接拍下来**。
没有表格、没有筛选、没有多级菜单。

## 进来有两条路

1. **系统相机 / 微信扫一扫**（推荐）：瓶身二维码里是一个 URL
   （``http://内网地址:8601/m?bottle=B-001``），扫完直接进本页并带上瓶号。
   印在瓶子上的地址来自「系统设置 → 手机访问地址」，或打印标签时选
   「跟随当前访问地址」。
2. **页内扫码**：码里是短码 ``BCLRM:B:B-001``，用本页摄像头扫。跳转目标
   永远是**当前这次访问的入口**（直连、SSH 隧道、反向代理都跟走），不看
   系统设置。受浏览器限制（``BarcodeDetector`` 只在安卓 Chrome 系可用），
   所以本页始终保留手输框——扫码是加速，不是唯一入口。

## 为什么页内扫码不用 CDN 上的 jsQR

实验室是内网，很多机器出不了外网。引一个 CDN 脚本的结果是「页面看着正常、
扫码永远不出结果」。所以只用浏览器原生的 ``BarcodeDetector``，不支持就
老实说「请用系统相机或手输」，不摆一个装样子的取景框。

## 照片按工单挂，不按瓶挂

同一瓶一年可能借出十次。按瓶挂照片，事后分不清哪张属于哪次交接；按工单挂，
「这张单发了多少、谁签的、现场什么样」永远在一起。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from business.evidence_service import (
    PHASE_BORROW,
    PHASE_LABELS,
    PHASE_RETURN,
    evidence_service,
)
from components.auth import require_auth, get_current_user
from components.sidebar_nav import render_sidebar
from config.settings import MOBILE_UI
from services.base.system_config_service import EvidenceConfig, system_config_service
from services.core.borrow_order_service import borrow_order_item_service
from services.core.reagent_bottle_service import reagent_bottle_service
from utils.photo_utils import human_size
from utils.qr_label import (
    app_root_of,
    human_expiry,
    normalize_base_url,
    parse_fields,
)

st.set_page_config(
    page_title="手机取证",
    page_icon="📷",
    layout="centered",
    # 现场是单手操作，侧栏默认收起；要看导航点左上角展开即可。
    initial_sidebar_state="collapsed",
)

# 直接执行本页（streamlit run views/14_手机取证.py）时的守卫：
# 环境关闭手机入口时，不渲染任何业务界面，只给固定提示（执行版 D11）。
if not MOBILE_UI:
    st.markdown("## 当前环境未开启手机取证")
    st.caption("手机取证仍是预研功能，未纳入本环境的发布范围。")
    st.caption("请在电脑端「领用归还」页上传交接照片；如有疑问请联系管理员。")
    st.stop()

if not require_auth():
    st.stop()

render_sidebar()
current_user = get_current_user() or ""

#: 「还在办」的工单状态。已归还 / 已驳回 / 已撤回 不再需要补拍。
_OPEN_ORDER_STATUSES = ("待审批", "借用中", "部分归还")


def _flash(level: str, message: str) -> None:
    """把提示留到下一次 rerun 显示。

    上传成功后必须 rerun 才能刷新照片墙，而 rerun 会把当前帧的 st.success
    冲掉——现场看到的结果会是「点了上传，什么都没发生」。所以先存进会话，
    下一页渲染时再显示。
    """
    st.session_state["_m_flash"] = (level, message)


_m_flash = st.session_state.pop("_m_flash", None)
if _m_flash:
    _level, _text = _m_flash
    if _level == "warning":
        st.warning(_text)
    elif _level == "error":
        st.error(_text)
    else:
        st.success(_text)


def _render_html(markup: str) -> None:
    """把带脚本的 HTML 挂到页面上。

    ``st.components.v1.html`` 在 Streamlit 1.66 已标记弃用（它走 iframe，
    脚本被关在同源但独立的文档里，跳转要靠 ``window.top`` 绕）。``st.html``
    的 ``unsafe_allow_javascript`` 让脚本直接跑在主文档里，取景框与页面同源，
    ``window.location`` 就是当前页，不用再穿透 iframe。老版本退回去用组件。
    """
    if hasattr(st, "html"):
        st.html(markup, unsafe_allow_javascript=True)
    else:  # pragma: no cover - 仅在 Streamlit < 1.60 时走到
        st.components.v1.html(markup, height=380)


def _scanner_html(target_prefix: str) -> str:
    """内嵌扫码器。只用原生 BarcodeDetector，不可用就明说。"""
    return f"""
<div style="font-family:-apple-system,system-ui,sans-serif">
  <div id="m-scan-msg" style="font-size:13px;color:#666;margin-bottom:8px">正在启动摄像头…</div>
  <video id="m-scan-video" playsinline muted
         style="width:100%;max-width:360px;border-radius:12px;background:#000"></video>
</div>
<script>
(function() {{
  var msgEl = document.getElementById('m-scan-msg');
  var video = document.getElementById('m-scan-video');
  var base = {target_prefix!r};
  function say(t) {{ msgEl.textContent = t; }}
  if (!('BarcodeDetector' in window)) {{
    say('这个浏览器不支持网页扫码。请用手机相机扫瓶身二维码，或在下面手输瓶号。');
    video.style.display = 'none';
    return;
  }}
  navigator.mediaDevices.getUserMedia({{video: {{facingMode: 'environment'}}}})
    .then(function(stream) {{
      video.srcObject = stream;
      return video.play();
    }})
    .then(function() {{
      say('把瓶身二维码对准取景框');
      return new BarcodeDetector({{formats: ['qr_code', 'code_128', 'code_39', 'ean_13']}});
    }})
    .then(function(detector) {{
      function tick() {{
        detector.detect(video).then(function(codes) {{
          if (codes && codes.length) {{
            var text = codes[0].rawValue;
            say('识别到：' + text + '，正在跳转…');
            window.location.href = base + encodeURIComponent(text);
            return;
          }}
          requestAnimationFrame(tick);
        }}).catch(function() {{ requestAnimationFrame(tick); }});
      }}
      tick();
    }})
    .catch(function() {{
      say('打不开摄像头（内网 HTTP 下浏览器会拦）。请用手机相机扫瓶身二维码，或在下面手输瓶号。');
      video.style.display = 'none';
    }});
}})();
</script>
"""


def _bottle_card(bottle) -> None:
    """瓶信息：现场只需要认得出是这一瓶。"""
    remaining = getattr(bottle, "remaining_quantity", None)
    unit = getattr(bottle, "unit", "") or ""
    st.markdown(f"### {getattr(bottle, 'reagent_name', '') or '（未命名试剂）'}")
    left, right = st.columns(2)
    with left:
        st.metric("剩余量", f"{remaining:g} {unit}" if remaining is not None else "—")
    with right:
        st.metric("保管人", getattr(bottle, "manager", "") or "—")
    st.caption(
        f"瓶号 {getattr(bottle, 'bottle_number', '')}　"
        f"位置 {getattr(bottle, 'storage_location', '') or '—'}　"
        f"效期 {getattr(bottle, 'expiry_date', '') or '—'}"
    )


def _render_photos(order_number: str, phase: str, expanded: bool = False) -> None:
    photos = evidence_service.photos_of(order_number, phase)
    if not photos:
        return
    with st.expander(
        f"{PHASE_LABELS[phase]}照片（{len(photos)} 张）", expanded=expanded
    ):
        # 手机上两列已经是极限：三列时每张缩略图只有一百来像素，
        # 标签上的批号根本看不清，照片墙就失去意义了。
        cols = st.columns(2)
        for index, photo in enumerate(photos):
            with cols[index % 2]:
                # 照片墙读缩略图：一屏四张，原图要传 1.8 MB，缩略图 200 KB。
                # 手机流量和渲染时间都省在这里，不是省在压原图上。
                content = evidence_service.read_thumb(photo["stored_name"])
                if content:
                    # 照片可能是竖的，统一限宽，避免手机上被拉成一条
                    st.image(content, use_container_width=True)
                    st.caption(
                        f"{photo.get('created_at') or ''}"
                        f"　{human_size(photo.get('size_bytes'))}"
                    )

        # 缩略图看不清批号时，得能调出原图；手机上点不开新窗口，
        # 所以放在同一页里选一张看。
        if len(photos) > 1:
            pick = st.selectbox(
                "看原图",
                options=list(range(len(photos))),
                format_func=lambda i: (
                    f"第 {i + 1} 张　{photos[i].get('created_at') or ''}"
                ),
                key=f"m_pick_{phase}_{order_number}",
            )
        else:
            pick = 0
        full = evidence_service.read(photos[pick]["stored_name"])
        if full:
            st.image(full, use_container_width=True)
            st.download_button(
                "下载这张原图",
                data=full,
                file_name=photos[pick]["stored_name"],
                mime="image/jpeg",
                key=f"m_dl_{phase}_{order_number}",
                use_container_width=True,
            )


def _render_upload(order_number: str, phase: str, default_expanded: bool, key_suffix: str) -> None:
    required = evidence_service.require(phase)
    label = f"📷 补拍{PHASE_LABELS[phase]}" + ("（必填）" if required else "（可选）")
    with st.expander(label, expanded=default_expanded):
        if evidence_service.count(order_number, phase) > 0 and required:
            st.caption("这张单已经有照片了，可以继续补拍。")
        files = st.file_uploader(
            "拍照或选照片",
            accept_multiple_files=True,
            type=["jpg", "jpeg", "png", "webp"],
            key=f"m_up_{phase}_{order_number}_{key_suffix}",
        )
        st.caption(
            "只收 JPG / PNG / WebP。iPhone 请直接用相机拍，"
            "或先在相册里转成 JPG；HEIC 原图服务端打不开。"
        )
        if st.button(
            "上传",
            key=f"m_btn_{phase}_{order_number}_{key_suffix}",
            use_container_width=True,
        ):
            if not files:
                st.warning("还没选照片")
            else:
                with st.spinner("正在保存照片…"):
                    result = evidence_service.attach(
                        order_number, phase, files, current_user, note="手机取证"
                    )
                if result.success:
                    failed = (getattr(result, "data", None) or {}).get("failed") or []
                    if failed:
                        _flash(
                            "warning",
                            result.message + "；未保存：" + "；".join(failed),
                        )
                    else:
                        _flash("success", result.message)
                    st.rerun()
                else:
                    failed = (getattr(result, "data", None) or {}).get("failed") or []
                    st.error(
                        result.message
                        + ("；" + "；".join(failed) if failed else "")
                    )


# ---------------------------------------------------------------- 页面
st.markdown("## 📷 手机取证")
st.caption("扫瓶身二维码，或输入瓶号。照片会挂在这一瓶当前的那张单上。")

base_url = ""
_mobile_base_raw = system_config_service.get(EvidenceConfig.MOBILE_BASE_URL, "")
try:
    base_url = normalize_base_url(_mobile_base_raw)
except ValueError as _exc:
    st.warning(
        f"「手机访问地址」配置无效：{_exc}。"
        "页内扫码仍可用，但瓶身码不会指向本系统；请让超管到系统设置修正。"
    )

# 扫码进来时带 ?bottle=xxx，预填到输入框。
#
# **不能每帧都预填**：用户手输了一个瓶号，下一帧重跑如果又被 query 参数
# 覆盖回去，人就没法改。所以只在「query 里的值变了」时填一次——扫码跳转是
# 一次新的页面加载，值必然变；用户手输不会动 URL，就永远走不到这个分支。
_scanned_raw = (st.query_params.get("bottle") or "").strip()
if _scanned_raw and _scanned_raw != st.session_state.get("_m_qs_mark", ""):
    _scanned = parse_fields(_scanned_raw)
    st.session_state["m_bottle_input"] = _scanned.get("bottle", "")
    # 输入框里只放瓶号（一串短码在手机上看不清），但码上的 CAS / 效期 /
    # 名字记在会话里——这个页面最要紧的用途就是「库查不到这瓶」的时候。
    st.session_state["_m_scanned_fields"] = _scanned
    st.session_state["_m_qs_mark"] = _scanned_raw

bottle_number = ""

# 扫码器跳回「当前这次访问」的入口，而不是系统设置里那个固定地址。
#
# 现场可能是内网直连，也可能是 SSH 端口转发（http://localhost:8501）。
# 既然这一页已经打开了，说明手里这台设备能走通当前这条路；跳回配置里的
# 另一个地址反而可能打不开。固定地址只用于「印在瓶子上、给别的设备扫」。
_current_base = app_root_of(getattr(st.context, "url", "") or "")
_scanner_base = _current_base or base_url

with st.expander("📷 扫一张", expanded=not st.session_state.get("m_bottle_input")):
    prefix = (_scanner_base.rstrip("/") + "/m?bottle=") if _scanner_base else "/m?bottle="
    _render_html(_scanner_html(prefix))
    if not _scanner_base:
        st.caption(
            "页内扫码只认得出瓶号，跳转回当前访问地址；"
            "系统设置里的「手机访问地址」只影响印在瓶身上的二维码。"
        )

manual = st.text_input(
    "瓶号", key="m_bottle_input", placeholder="例如 202610230001"
)
# 拆全部字段而不是只取瓶号：短码里还带着 CAS、效期、试剂名，那是**系统挂掉
# 或断网时唯一能读到的信息**。查库成功时以库里为准，这里只作旁证。
scanned = parse_fields(manual.strip()) if manual and manual.strip() else {}
_cached = st.session_state.get("_m_scanned_fields") or {}
if _cached.get("bottle") and _cached.get("bottle") == scanned.get("bottle"):
    # 扫码跳转进来的：输入框只有瓶号，其余字段在上面那一步记着
    for _key in ("cas", "expiry", "name"):
        scanned[_key] = scanned.get(_key) or _cached.get(_key, "")
if scanned.get("bottle"):
    bottle_number = scanned["bottle"]

if not bottle_number:
    st.info("还没有选瓶。扫二维码，或在上面的输入框里填瓶号。")
    st.stop()

# 先按瓶号查，再按条码查——老标签上贴的可能是出厂条码
bottle = reagent_bottle_service.get_by_bottle_number(bottle_number)
if bottle is None:
    bottle = reagent_bottle_service.get_by_barcode(bottle_number)

if bottle is None:
    # 查不到还能说什么？说码上写着什么。这是标签存在的意义：瓶子掉了、
    # 账本没了，扫一下至少知道这是什么物质、哪天过期。
    offline = " · ".join(
        part for part in (
            scanned.get("name", ""),
            f"CAS {scanned['cas']}" if scanned.get("cas") else "",
            f"效期 {human_expiry(scanned.get('expiry', ''))}"
            if scanned.get("expiry") else "",
        ) if part
    )
    st.warning(f"没有这瓶：{bottle_number}。请核对瓶号，或先在「实时库存」里建档。")
    if offline:
        st.info(f"瓶身码上写着：{offline}")
    st.stop()

_bottle_card(bottle)
_real_expiry = human_expiry(scanned.get("expiry", ""))
if _real_expiry and _real_expiry != human_expiry(getattr(bottle, "expiry_date", "") or ""):
    st.caption(f"瓶身码上的效期是 {_real_expiry}，与系统里的不一致——以系统为准，建议重打标签。")
real_number = getattr(bottle, "bottle_number", "") or bottle_number

st.divider()

rows = borrow_order_item_service.list_by_bottle(real_number, limit=12)
open_rows = [row for row in rows if (row.get("order_status") or "") in _OPEN_ORDER_STATUSES]

if not open_rows:
    st.info("这瓶目前没有在办的工单。借出/归还取证需要先有工单。")
else:
    st.markdown("### 在办工单")
    for row in open_rows:
        order_number = row.get("order_number") or ""
        order_status = row.get("order_status") or ""
        with st.container(border=True):
            st.markdown(
                f"**{order_number}**　{row.get('order_type') or ''}"
                f"　{order_status}"
            )
            st.caption(
                f"领用人 {row.get('applicant') or '—'}　"
                f"领用 {row.get('borrow_qty')} {row.get('unit') or ''}　"
                f"已还 {row.get('returned_qty') or 0}"
                + (f"　{row.get('course_name')}" if row.get("course_name") else "")
            )
            # 只有一个阶段有意义：还在审批这一环就是借出，已经借出就是归还
            phase = (
                PHASE_RETURN
                if order_status in ("借用中", "部分归还")
                else PHASE_BORROW
            )
            if phase == PHASE_BORROW and order_status == "待审批":
                st.caption(
                    "这张单还没批准。现在拍的照片会作为借出取证的补充；"
                    "正式发料仍要在电脑端完成审批。"
                )
            _render_photos(order_number, phase, expanded=True)
            _render_upload(
                order_number,
                phase,
                default_expanded=evidence_service.count(order_number, phase) == 0,
                key_suffix="open",
            )

if rows and not open_rows:
    with st.expander("这瓶借过哪些单", expanded=False):
        # 手机上没有横向拖表格的习惯，一单一张卡比 8 列表格好读。
        for row in rows:
            _order_number = row.get("order_number") or ""
            with st.container(border=True):
                st.markdown(
                    f"**{_order_number}**　{row.get('order_type') or ''}"
                    f"　{row.get('order_status') or ''}"
                )
                st.caption(
                    f"领用人 {row.get('applicant') or '—'}　"
                    f"领用 {row.get('borrow_qty')} {row.get('unit') or ''}　"
                    f"已还 {row.get('returned_qty') or 0}"
                    + (f"　{row.get('course_name')}" if row.get("course_name") else "")
                )
                st.caption(
                    f"借出照片 {evidence_service.count(_order_number, PHASE_BORROW)} 张"
                    f"　归还照片 {evidence_service.count(_order_number, PHASE_RETURN)} 张"
                )

st.divider()
with st.expander("按工单号直接补拍（手上没有瓶子时）", expanded=False):
    st.caption(
        "现场信号差、照片在相册里没传上去，或者想给一张旧单补材料时用这里。"
        f"必拍设置：借出{'必拍' if evidence_service.require(PHASE_BORROW) else '可选'}，"
        f"归还{'必拍' if evidence_service.require(PHASE_RETURN) else '可选'}。"
    )
    target_order = st.text_input(
        "工单号", key="m_manual_order", placeholder="例如 BO20261023143000001"
    )
    if target_order.strip():
        target_phase = st.radio(
            "补哪个阶段",
            options=[PHASE_BORROW, PHASE_RETURN],
            format_func=lambda p: PHASE_LABELS[p],
            horizontal=True,
            key="m_manual_phase",
        )
        _render_photos(target_order.strip(), target_phase, expanded=True)
        _render_upload(
            target_order.strip(), target_phase, default_expanded=True, key_suffix="manual"
        )

st.divider()
st.caption("手机端只做现场取证；审批、改单、查账请回电脑端。")
st.page_link("views/0_首页.py", label="回首页", icon="🏠")
