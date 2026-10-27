"""试剂库管理系统 - 主应用入口（页面路由器）

使用 Streamlit 原生多页面应用（MPA）v2：st.navigation + st.Page 动态构建导航。

运行契约（docs/环境隔离与发布规划_执行版.md）：

- dev 启动时自动建表/迁移，保持本地开发手感；
- prod/beta 启动时**只校验**四库 schema 版本，不建表、不迁移（D14）；
  迁移由部署器停服冷备后通过 ``scripts/runtime_cli.py migrate`` 显式执行。
- 手机取证是预研功能（D11）：``BCLRM_MOBILE_UI=0`` 时不注册页面，
  直接访问 ``/m`` 得到一条固定中性提示，不出现空白或裸 404。
- beta 注入横幅与全屏水印（D12）。

权限规则：
- 未登录：隐藏导航栏，仅显示登录表单（此时各业务页均未注册，URL 直达也会被拒绝）
- 已登录：注册各业务页面；「系统设置」仅超级管理员可见，
  非超级管理员既看不到该栏目，也无法通过 URL 直达（未注册的页面会被拒绝并回到默认页）

启动命令：streamlit run app.py
"""
from urllib.parse import urlparse

import streamlit as st

from config.settings import (
    IS_BETA,
    IS_DEV,
    MOBILE_UI,
    SYSTEM_NAME,
    describe_runtime,
    ensure_data_dirs,
)
from components.auth import is_logged_in, render_login_form
from components.theme import apply_theme
from utils.error_handler import logger

st.set_page_config(
    page_title=SYSTEM_NAME,
    page_icon="🧪",
    layout="wide"
)

# 品牌换肤：设计包 token（assets/design/）注入一次，对全部页面与侧边栏生效
apply_theme()


@st.cache_resource
def _prepare_runtime():
    """启动自检与 schema 闸门。

    dev：建表 + 迁移 + 补默认配置；
    prod/beta：只读校验 release.json 声明的 schema map，不写库。
    """
    from db.database import init_all_schemas, validate_schemas

    if IS_DEV:
        ensure_data_dirs()
        init_all_schemas()
        # 系统配置的出厂默认值：只补缺、不覆盖。人工改过（哪怕改成空串）就不碰，
        # 否则每次启动都会把超管关掉的开关又打开。
        from services.base.system_config_service import ensure_defaults
        ensure_defaults()
        schema = {}
    else:
        schema = validate_schemas()

    schema_map = {name: int(info["user_version"]) for name, info in (schema or {}).items()}
    logger.info("启动自检 " + describe_runtime(schema_map or None))
    return schema_map


_prepare_runtime()


def _request_path() -> str:
    """当前请求的 URL 路径；取不到时返回空串。"""
    try:
        return urlparse(getattr(st.context, "url", "") or "").path or ""
    except Exception:
        return ""


def _is_mobile_route() -> bool:
    return _request_path().rstrip("/").endswith("/m")


def _render_mobile_disabled() -> None:
    """手机关闭时的固定提示：不空白、不裸 404、不泄露业务数据。"""
    st.markdown("## 当前环境未开启手机取证")
    st.caption("手机取证仍是预研功能，未纳入本环境的发布范围。")
    st.caption("请在电脑端「领用归还」页上传交接照片；如有疑问请联系管理员。")


def _render_beta_watermark() -> None:
    """beta 横幅 + 全屏斜纹水印 + 角标。

    只用普通 markdown 与 CSS，不依赖 Streamlit 私有 DOM；
    ``pointer-events: none`` 保证不挡点击，也不改变布局。
    """
    st.markdown(
        """
<style>
.bclrm-beta-banner {
    position: relative;
    z-index: 2;
    margin: 0 0 .75rem 0;
    padding: .5rem 1rem;
    border-radius: .375rem;
    background: #FFF7E6;
    border: 1px solid #FFB020;
    color: #8C4A00;
    font-size: 14px;
    font-weight: 600;
}
.bclrm-beta-watermark {
    position: fixed;
    inset: 0;
    z-index: 9999;
    pointer-events: none;
    background-image: repeating-linear-gradient(
        -45deg,
        rgba(255, 176, 32, .07) 0,
        rgba(255, 176, 32, .07) 1px,
        transparent 1px,
        transparent 14px
    );
    display: flex;
    align-items: center;
    justify-content: center;
}
.bclrm-beta-watermark span {
    transform: rotate(-24deg);
    font-size: 46px;
    font-weight: 700;
    letter-spacing: .35em;
    color: rgba(255, 122, 0, .13);
    white-space: nowrap;
    user-select: none;
}
</style>
<div class="bclrm-beta-banner">测试环境 BETA：此处数据会在下次候选发布时清空，不作为正式台账。</div>
<div class="bclrm-beta-watermark" aria-hidden="true"><span>测试环境 BETA · 测试环境 BETA</span></div>
""",
        unsafe_allow_html=True,
    )


if IS_BETA:
    _render_beta_watermark()

# 手机关闭时不注册 /m：直接给固定提示，避免空白页或裸 404（D11）。
if not MOBILE_UI and _is_mobile_route():
    _render_mobile_disabled()
    st.stop()


def _login_page():
    """未登录时展示的登录页"""
    from utils.user_context import clear_user
    clear_user()  # 未登录状态：清空服务端权限守卫上下文
    st.markdown(f"## 🧪 {SYSTEM_NAME}")
    st.markdown("请先登录后使用系统。")
    render_login_form()


# ---------- 页面定义（路径相对入口文件）----------
_home_page = st.Page("views/0_首页.py", title="首页", icon="🏠", default=True)

_common_pages = [
    st.Page("views/1_实时库存.py", title="实时库存", icon="📦"),
    st.Page("views/2_试剂入库.py", title="试剂入库", icon="➕"),
    st.Page("views/3_领用归还.py", title="领用归还", icon="📤"),
    st.Page("views/4_综合查询.py", title="综合查询", icon="🔍"),
    st.Page("views/5_数据看板.py", title="数据看板", icon="📊"),
    st.Page("views/9_学期用量.py", title="学期用量", icon="📈"),
    st.Page("views/10_课程管理.py", title="课程管理", icon="📚"),
    st.Page("views/11_采购管理.py", title="采购管理", icon="🧾"),
    st.Page("views/12_试剂处置.py", title="试剂处置", icon="🧰"),
    st.Page("views/13_配方与需求.py", title="配方与需求", icon="⚗️"),
    st.Page("views/7_化学品信息管理.py", title="化学品信息管理", icon="🧪"),
    st.Page("views/8_管控化学品目录.py", title="管控化学品目录", icon="📋"),
]

# 手机端入口：url_path="m" 让瓶身二维码可以写成 http://内网地址:8601/m?bottle=xxx
# 短路径是刻意的——标签要打印、要手输、要能在手机键盘上敲完。
# 预研阶段默认关闭；关闭时不注册，避免生产界面出现手机入口（D11）。
_mobile_page = None
if MOBILE_UI:
    _mobile_page = st.Page(
        "views/14_手机取证.py", title="手机取证", icon="📷", url_path="m"
    )
    _common_pages.append(_mobile_page)

_settings_page = st.Page("views/6_系统设置.py", title="系统设置", icon="⚙️")

# 管理员的受理台：教师不接单，也不该看见这两个入口
#   待办队列 = 「谁该发料」（申请人的单排成一队）
#   调配台   = 「谁该点头」（管理员之间调保管权）
_admin_pages = [
    st.Page("views/15_待办队列.py", title="待办队列", icon="📋"),
    st.Page("views/16_调配台.py", title="调配台", icon="🔀"),
]


if not is_logged_in():
    # 未登录：隐藏导航组件，仅渲染登录页。
    #
    # /m 必须一起注册（手机开启时）：手机扫瓶身码进来时通常还没登录，若这里
    # 只注册登录页，当前路径会被回落到默认页，登录后不一定能回到「这一瓶」。
    # 页面自己会调 require_auth()，未登录时只显示登录表单，不会泄露业务数据。
    _login_pages = [st.Page(_login_page, title="登录", icon="🔑")]
    if _mobile_page is not None:
        _login_pages.append(_mobile_page)
    st.navigation(_login_pages, position="hidden").run()
else:
    pages = [_home_page] + _common_pages
    # 仅管理员注册受理台（待办队列 + 调配台）
    if st.session_state.get("user_role") in ("admin", "super_admin"):
        pages += _admin_pages
    # 仅超级管理员注册「系统设置」页面
    if st.session_state.get("user_role") == "super_admin":
        pages.append(_settings_page)
    st.navigation(pages).run()
