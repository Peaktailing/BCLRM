"""用户手册渲染前的按开关裁剪。

手机取证是开发预研（执行版 5.2 / D11）：生产口径下入口、标签、配置都不出现，
手册里也不该留一节教人扫码拍照。手册文件本身仍是唯一事实源，这里只在渲染
前裁掉「手机取证」标题下的整节，以及提到它的表格行/正文行。

为什么要按标题级别判断结束：手册将来可能在这一节里加子标题（``####``），
简单遇到下一个 ``#`` 就停会把子标题之后的内容漏出去。只到同级或更高级标题
才算这一节结束。
"""
from typing import List

MOBILE_MARKER = "手机取证"


def _heading_level(line: str) -> int:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return 0
    return len(stripped) - len(stripped.lstrip("#"))


def hide_mobile_sections(markdown: str) -> str:
    """去掉与手机取证相关的章节与零散引用，其余内容原样保留。"""
    if not markdown:
        return markdown

    kept: List[str] = []
    skip_level = 0  # >0 表示正在跳过某一节；值为该节标题级别
    for line in markdown.splitlines():
        level = _heading_level(line)
        if level:
            if skip_level and level <= skip_level:
                skip_level = 0
            if MOBILE_MARKER in line:
                skip_level = level
                continue
        if skip_level:
            continue
        # 表格行 / 正文里的零散引用（如入口一览表）也一并藏掉
        if MOBILE_MARKER in line:
            continue
        kept.append(line)

    text = "\n".join(kept)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text
