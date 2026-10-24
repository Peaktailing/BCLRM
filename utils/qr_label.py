"""瓶身二维码：把「手机扫一下就能办」变成一条贴纸。

手机上办借还，最难的一步是**说出是哪一瓶**。手输 ``B-20261023-001`` 在
4 寸屏上是二十几次点击加两次切键盘，现场没人愿意干。所以瓶身得有个码。

## 码里放什么

两种，按有没有配「手机访问地址」决定：

1. **配了** → 放一个完整 URL：``http://192.168.1.10:8601/m?bottle=202610230001``。
   手机用**系统相机或微信扫一扫**就能打开，不需要页面里再实现一个扫码器。
   这是首选：零 JS、零兼容性问题，iOS 微信也能用。**URL 只带瓶号**——
   URL 模式的前提是能联网，联网就该问系统，而不是让码替系统记档案。
2. **没配** → 放短码 ``BCLRM:2:202610230001;64-17-5;2026-10-23``（瓶号 /
   CAS / 入库日期，字段可空）。此时必须用页面里的扫码器解析。

短码是退路，但它比 URL 多背了信息：内网地址会变（换路由器、换服务器），
昨天打印的标签今天就打不开了；短码永远有效，而且**不依赖系统活着**。所以
短码里带 CAS 与入库日期不是冗余，是刻意的：瓶子漏了、仓库着火了、或者被
人从柜子里拿错，用任意扫码工具（微信、系统相机）扫一下就能读出「这是什么
物质、哪天进来的」——那正是系统宕机、断网、或者根本没登账号的时候。

两条都支持的另一个原因是**纸质标签会旧**。贴上去的标签可能用两年，而
服务器 IP 半年就变一次。所以 :func:`parse_fields` 三种都认（URL / v2 短码 /
v1 老短码），页面拿到哪种都能用。

## 为什么不用「编号即内容」

把裸瓶号当二维码内容看起来更简单，但扫出来是一串没人认识的字，系统之外的
工具（手机相机、微信）打开会说「无法识别」。带上 ``BCLRM:2:`` 前缀或是 URL，
至少能被人看出这是本系统的码——出事时捡到一张掉落的标签，也知道去哪查。

## 为什么字段之间用分号

瓶号是 ``YYYYMMDD`` + 4 位序号（12 位纯数字），CAS 是 ``64-17-5``，日期是
``2026-10-23``，三者都不含分号，用 ``;`` 分割不会歧义。逗号不行——有些
扫码工具会把含逗号的内容当 CSV 预览；``|`` 在部分机型上被转义成 ``%7C``。

**空字段保留位置**：CAS 缺失时写 ``; ;`` 而不是直接省掉，因为 ``parse_fields``
按位置取值——省掉位置会把日期读成 CAS。

## 能装多少，取决于「印多大」

二维码的容量表容易让人误判：版本 40 能装 2953 字节，但那是 177×177 个模块，
按手机能对准的最小模块 0.4 mm 印出来要 **71 mm 见方**——贴不到试剂瓶上。
真正约束是**物理尺寸**，字节数是推导出来的：

    模块边长(mm) = 打印边长(mm) / (模块数 + 静区)

经验阈值：≥0.45 mm 手机一扫即中；0.30–0.45 mm 要凑近、光线好；
<0.30 mm 小瓶标签上基本扫不动。:func:`fit` 就是把这笔账算给页面看，
让「地址太长导致码变密」在打印前就能发现，而不是贴到瓶上才发现扫不出。

按 19.5 mm 见方（本模块标签的实际尺寸）算：版本 4（62 字节）0.56 mm，
版本 7（122 字节）0.43 mm，版本 10（213 字节）0.34 mm，版本 15（412 字节）
已到 0.25 mm。也就是说 **19.5 mm 标签的现实预算是 ~120 字节**，
再多就得换更小的编码或更短的地址，而不是「反正二维码装得下」。
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from utils.error_handler import logger

#: v1 短码前缀（只有瓶号）。新标签不再生成，但老标签要认。
SHORT_PREFIX = "BCLRM:B:"

#: v2 短码前缀。后面跟 ``瓶号;CAS;入库日期``。
LONG_PREFIX = "BCLRM:2:"

#: 字段分隔符。三者都不含分号，见模块文档。
FIELD_SEP = ";"

#: 手机页的 URL 路径（与 ``st.Page(..., url_path=...)`` 保持一致）。
MOBILE_PATH = "/m"

#: 查询参数名。
BOTTLE_PARAM = "bottle"

#: 纠错等级。``m`` 能容忍约 15% 的面积污损——标签贴在试剂瓶上，被溅到、
#: 蹭掉角都是常态。再往上（Q/H）模块变密，小瓶上反而更难扫。
ERROR_LEVEL = "m"

#: 二维码四周的静区宽度（模块数）。规范要求 4，标签上白边够用 2 也行；
#: 这里用 1，靠标签底色当静区。
BORDER_MODULES = 1

#: 标签上二维码的打印边长（毫米）。480 px 宽的标签按 300 dpi 出图约 40 mm，
#: 码占宽度约一半。
QR_PRINT_MM = 19.5

#: 模块边长阈值（毫米）。低于前者要凑很近，低于后者基本扫不动。
GOOD_MODULE_MM = 0.45
TIGHT_MODULE_MM = 0.30


@dataclass(frozen=True)
class Fit:
    """一张码在某个打印尺寸下的物理账。

    Attributes:
        version: 二维码版本（1–40）
        modules: 含静区的模块数（边长上有几个方块）
        payload_bytes: 内容字节数
        error: 纠错等级
        module_mm: 单个模块的打印边长（毫米）
        grade: ``good`` / ``tight`` / ``too_small``
    """

    version: int
    modules: int
    payload_bytes: int
    error: str
    module_mm: float
    grade: str

    @property
    def readable(self) -> bool:
        return self.grade != "too_small"


def payload_of(
    bottle_number: str,
    base_url: str = "",
    cas: str = "",
    inbound_date: str = "",
) -> str:
    """生成二维码内容。

    Args:
        bottle_number: 瓶号
        base_url: 手机访问基地址（如 ``http://192.168.1.10:8601``）。空则出短码。
        cas: CAS 号（可为空；混合物、自制试剂、未建档的历史瓶没有）
        inbound_date: 入库日期 ``YYYY-MM-DD``（可为空）

    Returns:
        短码 ``BCLRM:2:<瓶号>;<CAS>;<入库日期>``，或 URL 形式。
        URL 只带瓶号——URL 的前提是能联网，联网就该问系统。
    """
    number = (bottle_number or "").strip()
    if not number:
        return ""
    base = (base_url or "").strip().rstrip("/")
    if base:
        return f"{base}{MOBILE_PATH}?{BOTTLE_PARAM}={quote(number, safe='')}"

    code = (cas or "").strip()
    day = (inbound_date or "").strip()
    if not code and not day:
        return f"{LONG_PREFIX}{number}"
    # 尾部空段可以省（``a;b`` 与 ``a;b;`` 等价），中间的不能省——
    # 省掉位置会把日期读成 CAS。
    tail = f"{code}{FIELD_SEP}{day}" if day else code
    return f"{LONG_PREFIX}{number}{FIELD_SEP}{tail}"


def parse_fields(text: str) -> Dict[str, str]:
    """把扫到的内容拆成字段。认不出返回空字典。

    返回值键：``bottle`` / ``cas`` / ``inbound``。老短码与 URL 只有瓶号，
    另两个字段给空串——调用方不必判断「这个码是哪一版」。

    认四种：v2 短码、v1 老短码、本模块生成的 URL、裸瓶号（有人拿瓶号直接
    生成码，或者手工输入）。
    """
    raw = unquote((text or "").strip())
    if not raw:
        return {}
    if raw.startswith(LONG_PREFIX):
        parts = raw[len(LONG_PREFIX):].split(FIELD_SEP)
        number = (parts[0] if parts else "").strip()
        if not number:
            return {}
        return {
            "bottle": number,
            "cas": (parts[1] if len(parts) > 1 else "").strip(),
            "inbound": (parts[2] if len(parts) > 2 else "").strip(),
        }
    if raw.startswith(SHORT_PREFIX):
        number = raw[len(SHORT_PREFIX):].strip()
        return {"bottle": number, "cas": "", "inbound": ""} if number else {}
    if "://" in raw or raw.startswith("/"):
        try:
            query = parse_qs(urlparse(raw).query)
        except ValueError:
            return {}
        values = query.get(BOTTLE_PARAM) or []
        if values and values[0].strip():
            return {"bottle": values[0].strip(), "cas": "", "inbound": ""}
        return {}
    # 裸瓶号：收下，但只当它是瓶号——页面查不到会说「没有这瓶」
    return {"bottle": raw, "cas": "", "inbound": ""}


def parse(text: str) -> Optional[str]:
    """从扫到的内容里取出瓶号。认不出返回 None。

    只取瓶号：页面拿到瓶号就能查库，CAS 与入库日期以库里为准——码里那份
    是「离线时给人看」的，不能拿来覆盖账本。
    """
    return parse_fields(text).get("bottle") or None


def _make(payload: str, error: str = ERROR_LEVEL):
    """建码。``boost_error=False`` 是必须的。

    默认 segno 会「顺便」把纠错等级往上提——内容少的时候提到 Q/H，看起来
    白赚。但等级一升，模块数跟着涨（同一段 URL：M 是 33 模块，H 是 41），
    小瓶标签上每模块就更小。标签的瓶颈是物理尺寸，不是纠错余量，
    所以按声明的等级来，别偷偷加密。
    """
    import segno

    return segno.make(payload, error=error, boost_error=False)


def fit(
    payload: str,
    error: str = ERROR_LEVEL,
    code_mm: float = QR_PRINT_MM,
) -> Optional[Fit]:
    """这笔内容印在 ``code_mm`` 见方时，单个模块有多大、能不能扫。

    Args:
        payload: 二维码内容
        error: 纠错等级
        code_mm: 打印边长（毫米，含静区）

    Returns:
        :class:`Fit`；内容为空或没装 segno 时返回 None
    """
    if not payload:
        return None
    try:
        code = _make(payload, error=error)
    except ImportError:  # pragma: no cover
        return None
    except Exception as exc:
        logger.warning(f"二维码内容过长或非法：{exc}")
        return None
    modules = 21 + 4 * (code.version - 1) + 2 * BORDER_MODULES
    module_mm = float(code_mm) / modules if modules else 0.0
    if module_mm >= GOOD_MODULE_MM:
        grade = "good"
    elif module_mm >= TIGHT_MODULE_MM:
        grade = "tight"
    else:
        grade = "too_small"
    return Fit(
        version=int(code.version),
        modules=modules,
        payload_bytes=len(payload.encode("utf-8")),
        error=error,
        module_mm=round(module_mm, 3),
        grade=grade,
    )


def png_bytes(
    payload: str, scale: int = 6, border: int = BORDER_MODULES
) -> Optional[bytes]:
    """生成二维码 PNG 字节。内容为空或库缺失时返回 None。"""
    if not payload:
        return None
    try:
        code = _make(payload)
    except ImportError:  # pragma: no cover - 环境缺失才会走到
        logger.warning("未安装 segno，无法生成二维码")
        return None
    except Exception as exc:
        logger.warning(f"二维码生成失败：{exc}")
        return None
    buffer = io.BytesIO()
    code.save(buffer, kind="png", scale=max(1, int(scale)), border=border)
    return buffer.getvalue()


def label_png(
    bottle_number: str,
    extra: str = "",
    payload: str = "",
    width: int = 480,
    cas: str = "",
    inbound_date: str = "",
) -> Optional[bytes]:
    """生成一张可打印的标签：二维码 + 瓶号 + 物质信息。

    尺寸按 300 dpi 下约 40×30 mm 出，贴 100 mL 试剂瓶刚好；更大的瓶
    看着空，但统一尺寸比「按瓶定制」好管理。

    **码按整数倍模块尺寸直接生成，不做缩放**。先把码画大再用 LANCZOS 缩到
    目标宽度，模块边界会变成半灰的斜边——屏幕上看只是「有点糊」，打印出来
    就是边缘模糊的方格，手机对焦时容易判错。整数倍缩放是二维码的硬要求。

    CAS 与入库日期既进码也印在标签上：码是给机器读的，字是给人读的——
    瓶子从架上拿下来那一刻，没人会先掏手机。
    """
    text = payload or payload_of(bottle_number, cas=cas, inbound_date=inbound_date)
    if not text:
        return None
    try:
        code = _make(text)
    except ImportError:  # pragma: no cover
        logger.warning("未安装 segno，无法生成二维码")
        return None
    except Exception as exc:
        logger.warning(f"二维码生成失败：{exc}")
        return None

    # 二维码占宽度的一半，右边留出写字的地方
    qr_box = int(width * 0.48)
    modules = 21 + 4 * (code.version - 1) + 2 * BORDER_MODULES
    scale = max(1, qr_box // modules)
    qr_px = modules * scale
    buffer = io.BytesIO()
    code.save(buffer, kind="png", scale=scale, border=BORDER_MODULES)
    code_bytes = buffer.getvalue()

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:  # pragma: no cover
        return code_bytes

    qr = Image.open(io.BytesIO(code_bytes)).convert("RGB")
    height = max(qr_px + 24, 210)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    canvas.paste(qr, (12, 12))

    draw = ImageDraw.Draw(canvas)
    font_big = _font(30)
    font_small = _font(20)
    font_tiny = _font(16)
    text_x = 12 + qr_px + 16
    draw.text((text_x, 16), bottle_number, fill=(0, 0, 0), font=font_big)

    y = 58
    if extra:
        # 长名字截断：标签上留一行，超出部分省略——打印出来反正看不清
        draw.text((text_x, y), extra[:14], fill=(60, 60, 60), font=font_small)
        y += 34
    if cas:
        draw.text((text_x, y), f"CAS {cas}", fill=(60, 60, 60), font=font_small)
        y += 30
    if inbound_date:
        draw.text(
            (text_x, y), f"入库 {inbound_date}", fill=(60, 60, 60), font=font_small
        )

    draw.text(
        (text_x, height - 34),
        "手机扫码办理",
        fill=(120, 120, 120),
        font=font_tiny,
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
    "LONG_PREFIX",
    "FIELD_SEP",
    "MOBILE_PATH",
    "BOTTLE_PARAM",
    "ERROR_LEVEL",
    "QR_PRINT_MM",
    "GOOD_MODULE_MM",
    "TIGHT_MODULE_MM",
    "Fit",
    "payload_of",
    "parse_fields",
    "parse",
    "fit",
    "png_bytes",
    "label_png",
]
