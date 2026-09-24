"""Code39 条码生成器（纯 Python 实现，无第三方条码库依赖）

生成可被普通一维扫码枪识别的 Code39 条码 PNG。
字符集：0-9 A-Z - . $ / + % 空格（起止符 * 自动添加）。
"""
import io
from typing import Optional

# Code39 编码表：9 个元素，奇数位为条、偶数位为空隙；n=窄 W=宽（宽是窄的 3 倍）
CODE39_PATTERNS = {
    '0': 'nnnwwnwnn', '1': 'wnnwnnnnw', '2': 'nnwwnnnnw', '3': 'wnwwnnnnn',
    '4': 'nnnwwnnnw', '5': 'wnnwwnnnn', '6': 'nnwwwnnnn', '7': 'nnnwnnwnw',
    '8': 'wnnwnnwnn', '9': 'nnwwnnwnn', 'A': 'wnnnnwnnw', 'B': 'nnwnnwnnw',
    'C': 'wnwnnwnnn', 'D': 'nnnnwwnnw', 'E': 'wnnnwwnnn', 'F': 'nnwnwwnnn',
    'G': 'nnnnnwwnw', 'H': 'wnnnnwwnn', 'I': 'nnwnnwwnn', 'J': 'nnnnwwwnn',
    'K': 'wnnnnnnww', 'L': 'nnwnnnnww', 'M': 'wnwnnnnwn', 'N': 'nnnnwnnww',
    'O': 'wnnnwnnwn', 'P': 'nnwnwnnwn', 'Q': 'nnnnnnwww', 'R': 'wnnnnnwwn',
    'S': 'nnwnnnwwn', 'T': 'nnnnwnwwn', 'U': 'wwnnnnnnw', 'V': 'nwwnnnnnw',
    'W': 'wwwnnnnnn', 'X': 'nwnnwnnnw', 'Y': 'wwnnwnnnn', 'Z': 'nwwnwnnnn',
    '-': 'nwnnnnwnw', '.': 'wwnnnnwnn', ' ': 'nwwnnnwnn', '$': 'wwnwwnnnn',
    '/': 'wwnwnnnnw', '+': 'wwnnwnnnw', '%': 'nwnwnwnnn', '*': 'nwnnwnwnn',
}

_VALID = set(CODE39_PATTERNS.keys())


def generate_code39_png(
    text: str,
    bar_height: int = 90,
    narrow: int = 2,
    show_text: bool = True,
) -> Optional[bytes]:
    """生成 Code39 条码 PNG

    Args:
        text: 条码内容（自动转大写；非法字符会被过滤）
        bar_height: 条高（像素）
        narrow: 窄元素宽度（像素）
        show_text: 是否在条码下方显示文本

    Returns:
        PNG 字节流；内容为空时返回 None
    """
    if not text:
        return None

    text = "".join(ch for ch in text.upper() if ch in _VALID)
    if not text:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = f"*{text}*"
    bars = []  # (x_start, width)
    x = 0
    for ch in data:
        pattern = CODE39_PATTERNS[ch]
        for i, elem in enumerate(pattern):
            width = narrow * (3 if elem == 'W' else 1)
            if i % 2 == 0:  # 奇数位为条
                bars.append((x, width))
            x += width
        x += narrow  # 字符间空隙
    total_w = x

    fig, ax = plt.subplots(
        figsize=(total_w / 12, bar_height / 30), dpi=160
    )
    for bx, bw in bars:
        ax.axvspan(bx, bx + bw, color="black", linewidth=0)
    ax.set_xlim(0, total_w)
    ax.set_ylim(0, 1)
    ax.axis("off")
    if show_text:
        ax.text(
            total_w / 2, -0.22, text,
            ha="center", va="top", fontsize=15, family="monospace", color="black",
        )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
