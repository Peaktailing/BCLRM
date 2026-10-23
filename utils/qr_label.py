"""瓶身二维码：把「手机扫一下就能办」变成一条贴纸。

手机上办借还，最难的一步是**说出是哪一瓶**。手输 ``B-20261023-001`` 在
4 寸屏上是二十几次点击加两次切键盘，现场没人愿意干。所以瓶身得有个码。

## 码里放什么

两种，按有没有配「手机访问地址」决定：

1. **配了** → 放一个完整 URL：``http://192.168.1.10:8601/m?bottle=B-001``。
   手机用**系统相机或微信扫一扫**就能打开，不需要页面里再实现一个扫码器。
   这是首选：零 JS、零兼容性问题，iOS 微信也能用。
2. **没配** → 放短码 ``BCLRM:B:B-001``。此时必须用页面里的扫码器解析。
   短码是退路：内网地址会变（换路由器、换服务器），昨天打印的标签今天
   就打不开了；短码永远有效，只是多一步。

两条都支持的另一个原因是**纸质标签会旧**。贴上去的标签可能用两年，而
服务器 IP 半年就变一次。所以 :func:`parse` 两种都认，页面拿到哪种都能用。

## 为什么不用「编号即内容」

把裸瓶号当二维码内容看起来更简单，但扫出来是一串没人认识的字，系统之外的
工具（手机相机、微信）打开会说「无法识别」。带上 ``BCLRM:B:`` 前缀或是 URL，
至少能被人看出这是本系统的码——出事时捡到一张掉落的标签，也知道去哪查。
"""
from __future__ import annotations

import io
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from utils.error_handler import logger

#: 短码前缀。加前缀是为了让码「看得出属于谁」，也便于和裸编号区分。
SHORT_PREFIX = "BCLRM:B:"

#: 手机页的 URL 路径（与 ``st.Page(..., url_path=...)`` 保持一致）。
MOBILE_PATH = "/m"

#: 查询参数名。
BOTTLE_PARAM = "bottle"


def payload_of(bottle_number: str, base_url: str = "") -> str:
    """生成二维码内容。

    Args:
        bottle_number: 瓶号
        base_url: 手机访问基地址（如 ``http://192.168.1.10:8601``）。空则出短码。
    """
    number = (bottle_number or "").strip()
    if not number:
        return ""
    base = (base_url or "").strip().rstrip("/")
    if base:
        return f"{base}{MOBILE_PATH}?{BOTTLE_PARAM}={quote(number, safe='')}"
    return f"{SHORT_PREFIX}{number}"


def parse(text: str) -> Optional[str]:
    """从扫到的内容里取出瓶号。认不出返回 None。

    认三种：本函数生成的 URL、短码、以及裸瓶号（有人拿瓶号直接生成码，
    或者手工输入）。
    """
    raw = unquote((text or "").strip())
    if not raw:
        return None
    if raw.startswith(SHORT_PREFIX):
        number = raw[len(SHORT_PREFIX):].strip()
        return number or None
    if "://" in raw or raw.startswith("/"):
        try:
            query = parse_qs(urlparse(raw).query)
        except ValueError:
            return None
        values = query.get(BOTTLE_PARAM) or []
        if values and values[0].strip():
            return values[0].strip()
        return None
    # 裸瓶号：收下，但只当它是瓶号——页面查不到会说「没有这瓶」
    return raw


def png_bytes(payload: str, scale: int = 6, border: int = 2) -> Optional[bytes]:
    """生成二维码 PNG 字节。内容为空或库缺失时返回 None。"""
    if not payload:
        return None
    try:
        import segno
    except ImportError:  # pragma: no cover - 环境缺失才会走到
        logger.warning("未安装 segno，无法生成二维码")
        return None
    buffer = io.BytesIO()
    # error='m'：标签可能被试剂溅到、局部磨损，中等纠错留出容错余量。
    # 纠错等级越高码越密，贴在 20 mL 小瓶上会扫不动。
    segno.make(payload, error="m").save(
        buffer, kind="png", scale=scale, border=border
    )
    return buffer.getvalue()


def label_png(
    bottle_number: str,
    extra: str = "",
    payload: str = "",
    width: int = 480,
) -> Optional[bytes]:
    """生成一张可打印的标签：二维码 + 瓶号 + 一行补充信息。

    尺寸按 300 dpi 下约 40×24 mm 出，贴 100 mL 试剂瓶刚好；更大的瓶
    看着空，但统一尺寸比「按瓶定制」好管理。
    """
    code = png_bytes(payload or payload_of(bottle_number), scale=8, border=1)
    if not code:
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:  # pragma: no cover
        return code

    qr = Image.open(io.BytesIO(code)).convert("RGB")
    # 二维码占宽度的一半，右边留出写字的地方
    qr_size = int(width * 0.48)
    qr = qr.resize((qr_size, qr_size), Image.LANCZOS)

    height = max(qr_size + 24, 160)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    canvas.paste(qr, (12, 12))

    draw = ImageDraw.Draw(canvas)
    font_big = _font(30)
    font_small = _font(20)
    text_x = 12 + qr_size + 16
    draw.text((text_x, 20), bottle_number, fill=(0, 0, 0), font=font_big)
    if extra:
        # 长名字截断：标签上留两行，超出部分省略——打印出来反正看不清
        draw.text((text_x, 64), extra[:18], fill=(60, 60, 60), font=font_small)
    draw.text(
        (text_x, height - 40),
        "手机扫码办理",
        fill=(120, 120, 120),
        font=font_small,
    )

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _font(size: int):
    """找一个能显示中文的字体；找不到就用默认位图字体（英文可用）。"""
    try:
        from PIL import ImageFont
    except ImportError:  # pragma: no cover
        return None
    candidates = (
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ValueError):
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # 老版本 Pillow 不接受 size
        return ImageFont.load_default()


__all__ = [
    "SHORT_PREFIX",
    "MOBILE_PATH",
    "BOTTLE_PARAM",
    "payload_of",
    "parse",
    "png_bytes",
    "label_png",
]
