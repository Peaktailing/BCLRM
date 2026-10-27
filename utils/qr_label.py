"""瓶身二维码：把「手机扫一下就能办」变成一条贴纸。

手机上办借还，最难的一步是**说出是哪一瓶**。手输 ``202610230001`` 在
4 寸屏上是二十几次点击加两次切键盘，现场没人愿意干。所以瓶身得有个码。

## 码里放什么

两种，按有没有配「手机访问地址」决定：

1. **配了** → 放一个完整 URL：``http://192.168.1.10:8601/m?bottle=202610230001``。
   手机用**系统相机或微信扫一扫**就能打开，不需要页面里再实现一个扫码器。
   这是首选：零 JS、零兼容性问题，iOS 微信也能用。**URL 只带瓶号**——
   URL 模式的前提是能联网，联网就该问系统，而不是让码替系统记档案。
2. **没配** → 放短码，当前是 v3：
   ``BCLRM:3:202610230001;64-17-5;202706;乙醇``（瓶号 / CAS / 效期 / 试剂名）。

短码是退路，但它比 URL 多背了信息：内网地址会变（换路由器、换服务器），
昨天打印的标签今天就打不开了；短码永远有效，而且**不依赖系统活着**。所以
短码里带 CAS、效期与名字不是冗余，是刻意的：瓶子漏了、仓库着火了、或者被
人从柜子里拿错，用任意扫码工具（微信、系统相机）扫一下就能读出「这是什么
物质、什么时候过期」——那正是系统宕机、断网、或者根本没登账号的时候。

四种格式都支持的另一个原因是**纸质标签会旧**。贴上去的标签可能用两年，而
服务器 IP 半年就变一次。所以 :func:`parse_fields` 四种都认（URL / v3 / v2 /
v1），页面拿到哪种都能用。

## 效期为什么到月，但年份必须写

供应商标签就只标到月：试剂盒上写的是「有效期至 2026-06」，没有日。系统里
``expiry_date`` 算到日（生产日期 + 品种保质期），那是**算出来的日**，不是
供应商承诺的日。码里写 ``202706`` 是如实记录精度；写 ``20270630`` 等于替
供应商编了一天。

但**年份不能省**。「短效试剂只印月和日」在纸面标签上勉强能读（今年 6 月底），
在码里不行，三条理由：

* 标签贴两年。明年扫到这瓶，``0630`` 是今年还是明年？
* 短效试剂一年进好几批，同一物质几个效期都挤在同一年，去掉年份全糊成一团。
* 省不出字数。实测 19.5 mm 标签上「到日」能放 22 个汉字，「到月」23 个——
  容量卡在版本边界，省 4 个字节跨不过去。

所以码里写全 ``YYYYMM``，但**标签上印给人看的字可以短**：``效 27.06`` 比
``效期 2026-06-30`` 短一半，两位年已经够定位，且不会误读。

## 为什么不用「编号即内容」

把裸瓶号当二维码内容看起来更简单，但扫出来是一串没人认识的字，系统之外的
工具（手机相机、微信）打开会说「无法识别」。带上 ``BCLRM:3:`` 前缀或是 URL，
至少能被人看出这是本系统的码——出事时捡到一张掉落的标签，也知道去哪查。

## 为什么字段之间用分号

瓶号是 ``YYYYMMDD`` + 4 位序号（12 位纯数字），CAS 是 ``64-17-5``，效期是
``202706``，三者都不含分号。逗号不行——有些扫码工具会把含逗号的内容当 CSV
预览；``|`` 在部分机型上被转义成 ``%7C``。

**试剂名放最后一段**，解析时只切前三刀。名字里万一有分号（真实数据里没见
过，但不能赌），从前面定长切开、剩下全部归名字，解析不会错位。

**空字段保留位置**：CAS 缺失时写 ``;;`` 而不是直接省掉，因为 ``parse_fields``
按位置取值——省掉位置会把效期读成 CAS。

## 汉字要几个字节

UTF-8 里一个汉字 3 字节。**但 segno 会在你不注意时用 Shift-JIS 把汉字压成
2 字节**——只要内容里有中文、又没显式指定 ``encoding``，它就这么干。省三分
之一容量，代价是解码器得自己猜编码：zxing 猜得对，iOS 相机和微信扫一扫不
一定有这个本事。码贴在瓶上要用两年，不该赌这一点。所以 :func:`_make` 在
内容含非 ASCII 时**显式**声明 UTF-8 + ECI。

按 3 字节/字算，19.5 mm 标签带 CAS 与效期时名字能放 23 个汉字。这个数字够
用：本系统 281 个试剂名的中位数是 5 字，94% 在 12 字以内，23 字覆盖 97.9%。
剩下那 6 个长名字全是「长系统名 + 括号缩写」的结构（``…(DTNB)``、
``…(EGTA)``），所以 :func:`truncate_name` 的规则是**优先保留括号里的缩写**。

## 能装多少，取决于「印多大」

二维码的容量表容易让人误判：版本 40 能装 2953 字节，但那是 177×177 个模块，
按手机能对准的最小模块 0.4 mm 印出来要 **71 mm 见方**——贴不到试剂瓶上。
真正约束是**物理尺寸**，字节数是推导出来的：

    模块边长(mm) = 打印边长(mm) / (模块数 + 静区)

经验阈值：≥0.45 mm 手机一扫即中；0.30–0.45 mm 要凑近、光线好；
<0.30 mm 小瓶标签上基本扫不动。:func:`fit` 就是把这笔账算给页面看，
让「地址太长导致码变密」在打印前就能发现，而不是贴到瓶上才发现扫不出。

按 21.8 mm 见方（``QR_BOX_RATIO`` 0.58 下的实际边长）算：版本 4（62 字节）
0.62 mm，版本 6（106 字节）0.51 mm，版本 8（152 字节）0.43 mm，版本 10
（213 字节）0.37 mm。也就是说**现实预算是 ~106 字节**，再多就得换更小的
编码或更短的地址，而不是「反正二维码装得下」。

## 为什么要算「实际出图」而不是名义尺寸

码得按**整数倍模块**生成（缩放会把模块边界插值成半灰的斜边，打印出来手机
判错），所以 ``scale = 可用像素 / 模块数`` 这一步必然有取整损失：名义
19.5 mm 的格子，51 个模块配 5 倍缩放，实际只有 21.6 mm。:func:`label_fit`
按 :func:`label_png` 的真实排版算，页面上的容量体检用它，才不会报「舒适」
而打出来「勉强」。
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse

from utils.error_handler import logger

#: v1 短码前缀（只有瓶号）。新标签不再生成，但老标签要认。
SHORT_PREFIX = "BCLRM:B:"

#: v2 短码前缀。后面跟 ``瓶号;CAS;入库日期``。
LONG_PREFIX = "BCLRM:2:"

#: v3 短码前缀（当前）。后面跟 ``瓶号;CAS;效期YYYYMM;试剂名``。
V3_PREFIX = "BCLRM:3:"

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

#: 码占标签宽度的比例。0.48 时 22 个字的码只有 0.42 mm/模块（掉出舒适区），
#: 0.58 能到 0.51 mm。右边仍留得下瓶号与三行小字。
QR_BOX_RATIO = 0.58

#: 标签上二维码的打印边长（毫米），对应 ``label_png`` 默认 480 px 宽、
#: 码占 58% 的情况。名义值，:func:`label_fit` 会算实际出图尺寸。
QR_PRINT_MM = 21.8

#: 模块边长阈值（毫米）。低于前者要凑很近，低于后者基本扫不动。
GOOD_MODULE_MM = 0.45
TIGHT_MODULE_MM = 0.30

#: 名字在码里最多留几个汉字（按 3 倍字节预算算）。19.5 mm 标签、
#: 带 CAS 与效期时的实测上限。
NAME_MAX_CHARS = 23

#: 标签排版假定 300 dpi（480 px 宽 ≈ 40.6 mm）。
LABEL_DPI = 300

#: 括号里像缩写的尾巴：``(TMB)`` / ``(DTNB)`` / ``（EGTA）``。
_TAIL_ABBR = re.compile(r"[（(]\s*([A-Za-z0-9\-',\s]{1,12}?)\s*[)）]\s*$")

#: 录入时带进来的多余空格：``联氮 - 二 (3 - 乙基…)``。只清连字符与括号
#: 周围那种，两个词之间的单空格不动（``乙酸 乙酯`` 是两个词，不能粘一起）。
_TIDY_DASH = re.compile(r"\s*([-－])\s*")
_TIDY_BRACKET = re.compile(r"\s*([()（）])\s*")

#: M 级纠错 byte 模式容量（字节）。版本 1–15，来自 ISO/IEC 18004 表 7。
_BYTE_CAPACITY_M = {
    1: 14, 2: 26, 3: 42, 4: 62, 5: 84, 6: 106, 7: 122, 8: 152, 9: 180,
    10: 213, 11: 251, 12: 287, 13: 331, 14: 362, 15: 412,
}


def _capacity_of(version: int) -> int:
    """版本 15 以上的粗估（规范表 7 的近似线性段，仅供提示）。"""
    return max(0, int(412 + (version - 15) * 60))


def _grade_of(module_mm: float) -> str:
    if module_mm >= GOOD_MODULE_MM:
        return "good"
    if module_mm >= TIGHT_MODULE_MM:
        return "tight"
    return "too_small"


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
        print_mm: 码在纸上实际占的边长（毫米）。按整数倍模块出图时它比名义
            尺寸小一点——:func:`fit` 里等于入参，:func:`label_fit` 里是真实值。
    """

    version: int
    modules: int
    payload_bytes: int
    error: str
    module_mm: float
    grade: str
    print_mm: float = 0.0

    @property
    def readable(self) -> bool:
        return self.grade != "too_small"

    @property
    def payload_capacity(self) -> int:
        """该版本在 M 级纠错下的 byte 模式容量（字节）。"""
        return _BYTE_CAPACITY_M.get(self.version, _capacity_of(self.version))

    @property
    def room_chars(self) -> int:
        """这码还能再塞几个汉字（按 3 字节/字估，页面提示用）。"""
        return max(0, (self.payload_capacity - self.payload_bytes) // 3)


def normalize_expiry(text: str) -> str:
    """把各种写法的效期归一成 ``YYYYMM``。认不出返回空串。

    供应商标签只标到月（``2026-06``），系统里 ``expiry_date`` 算到日
    （``2026-06-30``）。两种都收，统一截到月——**不补日、不猜日**，
    码里记录的是真实精度。

    >>> normalize_expiry("2026-06-30")
    '202606'
    >>> normalize_expiry("2027/11")
    '202711'
    >>> normalize_expiry("")
    ''
    """
    raw = re.sub(r"[^0-9]", "", (text or "").strip())
    if len(raw) >= 6:
        year, month = raw[:4], raw[4:6]
    elif len(raw) == 5:  # 2026-6 这种
        year, month = raw[:4], "0" + raw[4]
    else:
        return ""
    if not (1900 <= int(year) <= 2999):
        return ""
    if not (1 <= int(month) <= 12):
        return ""
    return f"{year}{month}"


def human_expiry(expiry: str) -> str:
    """把 ``202706`` 印成人读的短形式 ``27.06``。

    只留两位年。完整年份（``2026.06``）在这张 40 mm 宽的标签上会挤掉名字的
    位置，而两位年在 20 年内没有歧义——试剂不会放到 2126 年。
    """
    code = normalize_expiry(expiry)
    if len(code) != 6:
        return ""
    return f"{code[2:4]}.{code[4:6]}"


def tidy_name(name: str) -> str:
    """清掉录入时带进来的多余空格。

    真实数据里有 ``2,2'- 联氮 - 二 (3 - 乙基 - 苯并噻唑 - 6 - 磺酸) 二铵盐``
    这种名字——OCR 或手工录入把每个连字符和括号都加了空格，41 个字符里
    9 个是空格。清掉后 28 个字，标签上能多认出一截，码里也省十来个字节。

    只动**连字符与括号周围**的空格，两个词之间的单空格保留（``乙酸 乙酯``
    是两个不同的词，粘起来就成了另一个东西）。
    """
    text = (name or "").strip()
    if not text:
        return ""
    text = _TIDY_DASH.sub(r"\1", text)
    text = _TIDY_BRACKET.sub(r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def truncate_name(name: str, limit: int = NAME_MAX_CHARS) -> str:
    """把过长的试剂名截到能进码的长度。

    预算按**字节**算（``limit`` 个汉字 = 3×limit 字节），不是按字数：名字里
    混着 ``2-``、``(DTNB)`` 这类半角字符时，同样的字节预算能多放好几个字符。
    按字截会把 ``乙二醇双(2-氨基乙基醚)四乙酸`` 这种明明放得下的名字也砍掉。

    真实数据里超长的名字都是「长系统名 + 括号缩写」：``5,5'-二硫代双
    (2-硝基苯甲酸)(DTNB)``。括号里的缩写才是现场在叫的名字，所以**优先
    保留缩写**，其次在括号前断开，最后才硬截。动手前先 :func:`tidy_name`
    清空格——很多时候清完就装得下了。
    """
    text = tidy_name(name)
    budget = limit * 3
    if len(text.encode("utf-8")) <= budget:
        return text
    tail = _TAIL_ABBR.search(text)
    if tail:
        abbr = tail.group(1).strip()
        if abbr:
            return abbr if len(abbr.encode("utf-8")) <= budget else abbr[:budget] + "…"
    for opener in ("（", "("):
        cut = text.rfind(opener)
        if cut > 2 and len((text[:cut] + "…").encode("utf-8")) <= budget:
            return text[:cut].rstrip(" ,，、-") + "…"
    cut = text
    while len(cut) > 1 and len((cut + "…").encode("utf-8")) > budget:
        cut = cut[:-1]
    return cut + "…"


def normalize_base_url(raw: str) -> str:
    """把管理员填的「手机访问地址」收敛成 ``scheme://host[:port]``。

    这个值会被直接拼进瓶身二维码，**不能原样相信**：少一个 ``http://``，
    二维码扫出来就不是链接，手机相机只会显示一串文字；多一个 ``/m`` 或
    查询串，拼出来就是 ``/m/m?bottle=...``。因此保存前、出码前都走这里。

    规则：

    * 空串返回空串（表示走短码，不是错误）
    * 没写协议时补 ``http://``——内网地址通常就是 ``192.168.1.10:8601``
    * 只接受 http / https；不允许用户名密码；不允许路径（``/`` 与 ``/m``
      除外，``/m?bottle=...`` 这种测试链接也可以直接粘进来）
    * 端口必须是 1–65535 的整数

    Raises:
        ValueError: 地址不可用，消息可直接展示给管理员。
    """
    text = (raw or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    try:
        parsed = urlparse(text)
        # .port 在端口非法时会抛 ValueError，必须在这里取一次
        port = parsed.port
    except ValueError as exc:
        raise ValueError("地址格式不对，请检查主机名和端口") from exc

    if parsed.scheme not in ("http", "https"):
        raise ValueError("只支持 http:// 或 https:// 地址")
    if not parsed.hostname:
        raise ValueError("地址里没有主机名或 IP")
    if parsed.username or parsed.password:
        raise ValueError("地址里不要带用户名和密码")
    if any(ch.isspace() for ch in parsed.hostname):
        raise ValueError("主机名里不能有空格")

    path = (parsed.path or "").rstrip("/")
    if path not in ("", MOBILE_PATH):
        raise ValueError("只填到端口即可；路径只接受 /m")
    # 直接粘贴 /m?bottle=... 的测试链接时，查询串丢掉，只留基地址。
    if (parsed.query or parsed.fragment) and path != MOBILE_PATH:
        raise ValueError("地址里不要带 ? 或 # 后面的内容")

    if port is not None and not (1 <= port <= 65535):
        raise ValueError("端口必须在 1–65535 之间")

    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"  # IPv6 必须带方括号才能拼回 URL
    netloc = host if port is None else f"{host}:{port}"
    return f"{parsed.scheme}://{netloc}"


def app_root_of(url: str) -> str:
    """从浏览器当前页 URL 反推应用根地址，用于「跟随当前访问地址」。

    同一个程序可能通过内网 IP、SSH 隧道（``http://localhost:8501``）或反向
    代理访问。把其中任何一条写死，另外两条打印出来的码就打不开。这里取
    **用户此刻正在用的那一条**：去掉查询串，再去掉当前页面的那段路径。

    Streamlit 的页面路径只有一段（不允许 ``a/b``），所以去掉最后一段就是
    应用根；反向代理加的子路径（``https://host/lims``）会留在前面。

    Args:
        url: 一般是 ``st.context.url``。取不到时传空串即可。

    Returns:
        ``scheme://host[:port][/子路径]``；无法解析时返回空串，由调用方回退
        到固定地址或短码。

    Note:
        这是浏览器上报的值，只用来拼链接，**不能当权限或安全判断依据**。
    """
    text = (url or "").strip()
    if not text or "://" not in text:
        return ""
    try:
        parsed = urlparse(text)
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""

    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if port is None else f"{host}:{port}"

    path = (parsed.path or "").rstrip("/")
    if path:
        path = path.rsplit("/", 1)[0].rstrip("/")
    return f"{parsed.scheme}://{netloc}{path}"


def payload_of(
    bottle_number: str,
    base_url: str = "",
    cas: str = "",
    expiry: str = "",
    name: str = "",
) -> str:
    """生成二维码内容。

    Args:
        bottle_number: 瓶号
        base_url: 手机访问基地址（如 ``http://192.168.1.10:8601``）。空则出短码。
        cas: CAS 号（可为空；混合物、自制试剂、未建档的历史瓶没有）
        expiry: 效期，``2026-06`` / ``2026-06-30`` / ``202606`` 都收，统一到月
        name: 试剂名（可为空）。按 :data:`NAME_MAX_CHARS` 截断

    Returns:
        短码 ``BCLRM:3:<瓶号>;<CAS>;<效期>;<名>``，或 URL 形式。
        URL 只带瓶号——URL 的前提是能联网，联网就该问系统。
    """
    number = (bottle_number or "").strip()
    if not number:
        return ""
    try:
        base = normalize_base_url(base_url)
    except ValueError:
        # 配置页保存时会拦，这里只是防御旧配置/手改库：宁可回退短码，
        # 也不能把一条打不开的地址印到瓶子上。
        base = ""
    if base:
        return f"{base}{MOBILE_PATH}?{BOTTLE_PARAM}={quote(number, safe='')}"

    code = (cas or "").strip()
    month = normalize_expiry(expiry)
    label = truncate_name(name)
    if not code and not month and not label:
        return f"{V3_PREFIX}{number}"
    # 尾部空段可以省（``a;b`` 与 ``a;b;`` 等价），中间的不能省——
    # 省掉位置会把效期读成 CAS。
    fields = [number, code]
    if month or label:
        fields.append(month)
    if label:
        fields.append(label)
    return V3_PREFIX + FIELD_SEP.join(fields)


def _empty_fields() -> Dict[str, str]:
    """解析结果的统一形状。四种格式给同样的键，调用方不必判断版本。"""
    return {"bottle": "", "cas": "", "inbound": "", "expiry": "", "name": ""}


def parse_fields(text: str) -> Dict[str, str]:
    """把扫到的内容拆成字段。认不出返回空字典。

    返回值键：``bottle`` / ``cas`` / ``inbound`` / ``expiry`` / ``name``。
    版本差异体现在哪些键有值：v3 给 ``expiry`` 与 ``name``，v2 给
    ``inbound``，v1 与 URL 只给 ``bottle``——其余是空串，调用方不必判断
    「这个码是哪一版」。

    认五种：v3 短码、v2 短码、v1 老短码、本模块生成的 URL、裸瓶号（有人
    拿瓶号直接生成码，或者手工输入）。
    """
    raw = unquote((text or "").strip())
    if not raw:
        return {}

    for prefix, kind in ((V3_PREFIX, "v3"), (LONG_PREFIX, "v2")):
        if not raw.startswith(prefix):
            continue
        # 只切前三刀：名字放最后一段，名字里万一有分号也不会错位
        parts = raw[len(prefix):].split(FIELD_SEP, 3)
        number = (parts[0] if parts else "").strip()
        if not number:
            return {}
        fields = _empty_fields()
        fields["bottle"] = number
        fields["cas"] = (parts[1] if len(parts) > 1 else "").strip()
        third = (parts[2] if len(parts) > 2 else "").strip()
        if kind == "v3":
            fields["expiry"] = normalize_expiry(third)
            fields["name"] = (parts[3] if len(parts) > 3 else "").strip()
        else:
            fields["inbound"] = third
        return fields

    if raw.startswith(SHORT_PREFIX):
        number = raw[len(SHORT_PREFIX):].strip()
        if not number:
            return {}
        fields = _empty_fields()
        fields["bottle"] = number
        return fields

    if "://" in raw or raw.startswith("/"):
        try:
            query = parse_qs(urlparse(raw).query)
        except ValueError:
            return {}
        values = query.get(BOTTLE_PARAM) or []
        if values and values[0].strip():
            fields = _empty_fields()
            fields["bottle"] = values[0].strip()
            return fields
        return {}

    # 裸瓶号：收下，但只当它是瓶号——页面查不到会说「没有这瓶」
    fields = _empty_fields()
    fields["bottle"] = raw
    return fields


def parse(text: str) -> Optional[str]:
    """从扫到的内容里取出瓶号。认不出返回 None。

    只取瓶号：页面拿到瓶号就能查库，CAS / 效期 / 名字以库里为准——码里那份
    是「离线时给人看」的，不能拿来覆盖账本。
    """
    return parse_fields(text).get("bottle") or None


def _make(payload: str, error: str = ERROR_LEVEL):
    """建码。两个参数是必须的。

    ``boost_error=False``：默认 segno 会「顺便」把纠错等级往上提——内容少的
    时候提到 Q/H，看起来白赚。但等级一升，模块数跟着涨（同一段 URL：M 是
    33 模块，H 是 41），小瓶标签上每模块就更小。标签的瓶颈是物理尺寸，不是
    纠错余量，所以按声明的等级来，别偷偷加密。

    ``encoding="utf-8"`` + ``eci=True``（仅内容含非 ASCII 时）：不这么写，
    segno 会用 Shift-JIS 把汉字压成 2 字节，且**不在码里留编码标记**。省掉
    三分之一的容量，代价是解码器得猜——zxing 猜得对，手机相机不一定。码要
    贴两年，不赌这个。纯 ASCII 内容不加 ECI，老标签的字节一个都不变。
    """
    import segno

    kwargs = {"error": error, "boost_error": False}
    if not payload.isascii():
        kwargs["encoding"] = "utf-8"
        kwargs["eci"] = True
    return segno.make(payload, **kwargs)


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
    return Fit(
        version=int(code.version),
        modules=modules,
        payload_bytes=len(payload.encode("utf-8")),
        error=error,
        module_mm=round(module_mm, 3),
        grade=_grade_of(module_mm),
        print_mm=round(float(code_mm), 2),
    )


def label_layout(
    payload: str,
    width: int = 480,
    error: str = ERROR_LEVEL,
) -> Optional[Tuple[int, int, int, float]]:
    """算出 :func:`label_png` 里二维码的真实排版。

    Returns:
        ``(scale, qr_px, modules, print_mm)``；内容为空或生成失败返回 None。
        ``scale`` 是每个模块画几像素——必须是整数，否则模块边界会被插值成
        半灰的斜边，打印出来手机判错。
    """
    if not payload:
        return None
    try:
        code = _make(payload, error=error)
    except ImportError:  # pragma: no cover
        return None
    except Exception as exc:
        logger.warning(f"二维码生成失败：{exc}")
        return None
    modules = 21 + 4 * (code.version - 1) + 2 * BORDER_MODULES
    box = int(width * QR_BOX_RATIO)
    # round 而不是 floor：floor 在 51 模块时把码压到 21.6 mm（0.42 mm/模块），
    # 明明右边还有 30 px 没用上。允许略微超出 box，只要标签总宽放得下。
    scale = max(1, round(box / modules))
    qr_px = modules * scale
    return scale, qr_px, modules, qr_px * 25.4 / LABEL_DPI


def label_fit(
    payload: str,
    width: int = 480,
    error: str = ERROR_LEVEL,
) -> Optional[Fit]:
    """按标签的**真实排版**算容量，而不是名义尺寸。

    页面上的「装得下吗」要报这个数：名义 19.5 mm 的格子，实际出图常常
    只有 18 mm，判级会差一档。
    """
    layout = label_layout(payload, width=width, error=error)
    if layout is None:
        return None
    _scale, _px, modules, print_mm = layout
    try:
        code = _make(payload, error=error)
    except Exception:  # pragma: no cover - layout 已经成功过
        return None
    module_mm = print_mm / modules if modules else 0.0
    return Fit(
        version=int(code.version),
        modules=modules,
        payload_bytes=len(payload.encode("utf-8")),
        error=error,
        module_mm=round(module_mm, 3),
        grade=_grade_of(module_mm),
        print_mm=round(print_mm, 2),
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


def _fit_text(draw, text: str, max_width: int, start: int = 30):
    """挑一个能塞进 ``max_width`` 的字号。返回字体。"""
    size = start
    while size > 12:
        font = _font(size)
        try:
            width = draw.textlength(text, font=font)
        except Exception:  # pragma: no cover - 极老的 Pillow
            return font
        if width <= max_width:
            return font
        size -= 2
    return _font(12)


def _cut_to_width(draw, text: str, font, max_width: int) -> str:
    """按**像素**宽度截字，末尾补省略号。

    按字数截是靠不住的：``乙二醇双(2-氨基乙基醚)四乙酸`` 里既有汉字又有
    半角符号，同样 17 个字符，宽度能差一倍。标签右侧只有 184 px，按像素
    退字才不会溢出到纸外。
    """
    try:
        if draw.textlength(text, font=font) <= max_width:
            return text
    except Exception:  # pragma: no cover
        return text
    cut = text
    while len(cut) > 1:
        cut = cut[:-1]
        try:
            if draw.textlength(cut + "…", font=font) <= max_width:
                return cut + "…"
        except Exception:  # pragma: no cover
            return cut
    return text[:1]


def label_png(
    bottle_number: str,
    name: str = "",
    payload: str = "",
    width: int = 480,
    cas: str = "",
    expiry: str = "",
) -> Optional[bytes]:
    """生成一张可打印的标签：二维码 + 瓶号 + 试剂名 + CAS + 效期。

    尺寸按 300 dpi 下约 40×30 mm 出，贴 100 mL 试剂瓶刚好；更大的瓶
    看着空，但统一尺寸比「按瓶定制」好管理。

    **码按整数倍模块尺寸直接生成，不做缩放**。先把码画大再用 LANCZOS 缩到
    目标宽度，模块边界会变成半灰的斜边——屏幕上看只是「有点糊」，打印出来
    就是边缘模糊的方格，手机对焦时容易判错。整数倍缩放是二维码的硬要求。

    CAS、效期、名字既进码也印在标签上：码是给机器读的，字是给人读的——
    瓶子从架上拿下来那一刻，没人会先掏手机。效期只印 ``27.06`` 两位年，
    完整年份（``2026.06``）会把名字挤掉，而两位年在 20 年内没有歧义。
    """
    text = payload or payload_of(bottle_number, cas=cas, expiry=expiry, name=name)
    if not text:
        return None
    layout = label_layout(text, width=width)
    if layout is None:
        return None
    scale, qr_px, _modules, _print_mm = layout
    try:
        code = _make(text)
    except Exception as exc:  # pragma: no cover - layout 已经成功过
        logger.warning(f"二维码生成失败：{exc}")
        return None
    buffer = io.BytesIO()
    code.save(buffer, kind="png", scale=scale, border=BORDER_MODULES)
    code_bytes = buffer.getvalue()

    try:
        from PIL import Image, ImageDraw
    except ImportError:  # pragma: no cover
        return code_bytes

    qr = Image.open(io.BytesIO(code_bytes)).convert("RGB")
    month = human_expiry(expiry)
    lines = [line for line in (
        tidy_name(name),
        f"CAS {cas}" if cas else "",
        f"效 {month}" if month else "",
    ) if line]
    height = max(qr_px + 24, 210)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    canvas.paste(qr, (12, 12))

    draw = ImageDraw.Draw(canvas)
    font_name = _font(16)
    font_tiny = _font(16)
    text_x = 12 + qr_px + 14
    room = max(40, width - text_x - 12)
    font_big = _fit_text(draw, bottle_number, room, start=30)
    draw.text((text_x, 14), bottle_number, fill=(0, 0, 0), font=font_big)

    # 名字用深灰、CAS 与效期用中灰：同一字号靠颜色分层，省下的横向空间
    # 让名字多显示两三个字（16 px 下 184 px 能放 11 个汉字）。
    colors = ((40, 40, 40), (90, 90, 90), (90, 90, 90))
    y = 54
    for index, line in enumerate(lines):
        font = font_name if index == 0 else font_tiny
        draw.text(
            (text_x, y),
            _cut_to_width(draw, line, font, room),
            fill=colors[min(index, 2)],
            font=font,
        )
        y += 28 if index == 0 else 24

    draw.text(
        (text_x, height - 32),
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
    "V3_PREFIX",
    "FIELD_SEP",
    "MOBILE_PATH",
    "BOTTLE_PARAM",
    "ERROR_LEVEL",
    "QR_PRINT_MM",
    "QR_BOX_RATIO",
    "GOOD_MODULE_MM",
    "TIGHT_MODULE_MM",
    "NAME_MAX_CHARS",
    "Fit",
    "normalize_expiry",
    "human_expiry",
    "tidy_name",
    "truncate_name",
    "normalize_base_url",
    "app_root_of",
    "payload_of",
    "parse_fields",
    "parse",
    "fit",
    "label_layout",
    "label_fit",
    "png_bytes",
    "label_png",
]
