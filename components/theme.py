"""品牌主题组件

把设计包（docs/design_mockups/）里的 BCLRM 品牌样式应用到 Streamlit：

- assets/design/tokens.css       设计 token 唯一来源（颜色/圆角/阴影/字号/间距）
- assets/design/streamlit.css    token → Streamlit DOM 的换肤层
- .streamlit/config.toml         Streamlit 原生主题（主色、圆角、字号、侧边栏深灰）

调用位置：app.py 在 st.navigation(...).run() 之前执行 apply_theme()。
CSS 作用于整个页面文档（含侧边栏），因此一次注入即对全部页面生效。
"""
from pathlib import Path

import streamlit as st

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "design"
_CSS_FILES = ("tokens.css", "streamlit.css")

_cache: dict[str, str] = {}
_cache_stamp: tuple | None = None


def _theme_css() -> str:
    """读取并合并品牌样式（按文件修改时间缓存，改样式后刷新页面即生效）"""
    global _cache_stamp, _cache

    stamp = tuple(
        (name, _ASSETS_DIR.joinpath(name).stat().st_mtime_ns)
        if _ASSETS_DIR.joinpath(name).exists()
        else (name, 0)
        for name in _CSS_FILES
    )
    if stamp != _cache_stamp:
        _cache_stamp = stamp
        _cache.clear()
        _cache["css"] = "\n".join(
            path.read_text(encoding="utf-8")
            for name in _CSS_FILES
            if (path := _ASSETS_DIR / name).exists()
        )
    return _cache.get("css", "")


def apply_theme() -> None:
    """注入品牌样式

    Streamlit 每次交互都会重跑脚本并重建 DOM，因此每次运行都要注入；
    只在 app.py 调用一次即可，页面脚本无需重复调用。
    """
    css = _theme_css()
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def badge(text: str, kind: str = "neutral") -> str:
    """生成状态徽标的 HTML 片段，配合 st.markdown(..., unsafe_allow_html=True) 使用

    kind: success / warning / error / info / neutral / brand
    """
    safe_kind = kind if kind in {
        "success", "warning", "error", "info", "neutral", "brand"
    } else "neutral"
    safe_text = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f'<span class="bclrm-badge bclrm-badge--{safe_kind}">{safe_text}</span>'
