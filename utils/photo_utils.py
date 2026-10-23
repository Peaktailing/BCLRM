"""照片预处理：手机原图进来，压过再落盘。

手机拍的一张照片动辄 4–8 MB、4000×3000。现场取证一次能拍四五张，直接存
原始字节有三个后果：附件目录一个学期涨到几十 G、内网 Wi-Fi 上传要等半分
钟（人就不拍了）、页面里往前翻照片卡到没法用。而核对「这瓶是谁拿的」
根本不需要 1200 万像素。

所以统一做三件事：

1. **按 EXIF 方向转正**。手机竖着拍，像素其实是横的、靠 EXIF 的
   ``Orientation`` 标记让浏览器转过来。重编码会丢掉 EXIF，不先转正的话
   竖拍的照片在系统里全是躺着的——这个 bug 只有在手机上看才发现。
2. **长边压到 1600**。标签上的字在 1600 像素下仍然清晰，一张降到
   200–400 KB。
3. **重编码成 JPEG**。保留原始格式没意义：HEIC 浏览器显示不了，PNG 存
   照片体积反而更大。

**HEIC 的处置**：Pillow 默认不认 HEIC（需要 ``pillow-heif``）。iOS 在
``<input accept="image/jpeg">`` 下会转成 JPEG 再上传，所以正常路径碰不到。
真碰上了不静默失败——如实说「这个格式需要转换」，由调用方提示用户重拍，
而不是塞一个打不开的文件进附件目录。
"""
from __future__ import annotations

import io
from typing import Optional, Tuple

from utils.error_handler import logger

#: 长边上限。1600 是「标签上的小字仍可辨认」与「体积可接受」的交点。
DEFAULT_MAX_EDGE = 1600

#: 重编码质量。82 在照片上肉眼无损，再往上体积涨得快、收益很小。
DEFAULT_QUALITY = 82

#: 认得的输入扩展名。HEIC 故意不在内——见模块文档。
ALLOWED_EXTS = ("jpg", "jpeg", "png", "webp", "bmp")


class PhotoError(ValueError):
    """照片无法处理（格式不认、内容损坏）。"""


def _pil():
    """延迟导入 Pillow。

    图片处理只在取证路径上用，而 ``utils`` 被几乎所有模块导入——把 Pillow
    提到模块级会让命令行脚本、纯数据测试也背上这个依赖。
    """
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - 环境缺失才会走到
        raise PhotoError("未安装 Pillow，无法处理照片") from exc
    return Image, ImageOps


def normalize(
    data: bytes,
    max_edge: int = DEFAULT_MAX_EDGE,
    quality: int = DEFAULT_QUALITY,
) -> Tuple[bytes, Tuple[int, int]]:
    """把一张照片转正、缩放、重编码成 JPEG。

    Args:
        data: 原始字节
        max_edge: 长边上限（像素）。原图更小则不放大——放大只会变糊、变大。
        quality: JPEG 质量

    Returns:
        ``(jpeg_bytes, (宽, 高))``

    Raises:
        PhotoError: 不是图片、格式不认、或内容损坏
    """
    if not data:
        raise PhotoError("照片内容为空")
    Image, ImageOps = _pil()

    try:
        with Image.open(io.BytesIO(data)) as image:
            # 转正必须在 resize 之前：EXIF 的 90° 会让宽高互换，
            # 先缩放再转正会把长边算错。
            upright = ImageOps.exif_transpose(image)
            if upright is None:  # 极老的 Pillow 分支
                upright = image
            if upright.mode not in ("RGB", "L"):
                # RGBA / P / CMYK 一律铺白底转 RGB：直接 convert 会让
                # 透明区域变黑，贴在取证表上像一块污渍。
                background = Image.new("RGB", upright.size, (255, 255, 255))
                converted = upright.convert("RGBA")
                background.paste(converted, mask=converted.split()[-1])
                upright = background
            elif upright.mode == "L":
                upright = upright.convert("RGB")

            width, height = upright.size
            longest = max(width, height)
            if longest > max_edge > 0:
                ratio = max_edge / float(longest)
                new_size = (max(1, round(width * ratio)), max(1, round(height * ratio)))
                upright = upright.resize(new_size, Image.LANCZOS)

            out = io.BytesIO()
            upright.save(out, format="JPEG", quality=quality, optimize=True)
            return out.getvalue(), upright.size
    except PhotoError:
        raise
    except Exception as exc:
        logger.warning(f"照片处理失败：{exc}")
        raise PhotoError(f"照片无法识别：{exc}") from exc


def normalize_or_original(
    data: bytes,
    max_edge: int = DEFAULT_MAX_EDGE,
    quality: int = DEFAULT_QUALITY,
) -> Tuple[bytes, bool]:
    """尽量压缩；压不了就原样返回并标明「没压成」。

    取证这件事**不能因为压缩失败就丢证据**。一张处理不了的照片仍要存下来，
    只是告诉调用方体积没降——由它决定是否提示。
    """
    try:
        normalized, _ = normalize(data, max_edge=max_edge, quality=quality)
        return normalized, True
    except PhotoError as exc:
        logger.warning(f"照片压缩失败，按原样保存：{exc}")
        return data, False


def guess_ext(name: str, default: str = "jpg") -> str:
    """从文件名取扩展名（小写、无点）。"""
    text = (name or "").strip()
    if "." not in text:
        return default
    ext = text.rsplit(".", 1)[-1].lower()
    return ext or default


def is_supported(name: str) -> bool:
    return guess_ext(name) in ALLOWED_EXTS


def human_size(num_bytes: Optional[int]) -> str:
    """人看的大小。"""
    if not num_bytes:
        return "0 KB"
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


__all__ = [
    "PhotoError",
    "DEFAULT_MAX_EDGE",
    "DEFAULT_QUALITY",
    "ALLOWED_EXTS",
    "normalize",
    "normalize_or_original",
    "guess_ext",
    "is_supported",
    "human_size",
]
