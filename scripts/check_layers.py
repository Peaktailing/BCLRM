"""分层依赖体检：确认依赖只沿一个方向流动。

用法::

    python scripts/check_layers.py          # 列报告，违规时退出码 1
    python scripts/check_layers.py -v       # 连依赖明细一起打印

规则（依赖只能自上而下）::

    views  →  business  →  capabilities  →  domain
                              ↓
                       services / db / utils

为什么值得一个脚本而不是靠自觉：一次「图省事 import 了 db」就会让
领域层再也无法脱离数据库测试，而这种腐化在 code review 里极难看出来。
"""
from __future__ import annotations

import ast
import os
import sys
from typing import Dict, List, Set

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 每层允许导入的项目内顶层包；不在名单里的都算违规
ALLOWED: Dict[str, Set[str]] = {
    # 领域层：只认识自己（+ 标准库）。这是「零依赖」的技术保证。
    "domain": {"domain"},
    # 中台层：认识领域；工具层只用于日志（不得用于取数据）
    "capabilities": {"domain", "capabilities", "utils"},
    # 业务层：认识中台、领域、数据服务与工具；不认页面框架。
    # models 是 BCLRM 既有的「数据模型层」（dataclass + 字段常量），
    # 业务层取状态常量用，属既有惯例。
    "business": {"business", "capabilities", "domain", "services", "models", "utils"},
    # 数据层：认识库、领域、中台（适配器要造 StockSnapshot 等）；不认业务
    "services": {"services", "domain", "capabilities", "db", "models", "utils", "config"},
    # 表现层：都可以用
    "views": {"views", "components", "business", "capabilities", "domain", "services", "db", "utils", "config"},
    "components": {"components", "business", "services", "db", "utils", "config", "domain", "models"},
}

#: 项目内的顶层包（用于区分标准库/第三方）
PROJECT_PACKAGES = {"domain", "capabilities", "business", "services", "views", "components", "db", "utils", "config", "models"}

#: 额外禁止：某层不得出现的具体模块
EXTRA_FORBIDDEN: Dict[str, Set[str]] = {
    "domain": {"streamlit", "pandas", "sqlite3", "flask"},
    "capabilities": {"streamlit", "pandas"},
    "business": {"streamlit", "pandas"},
    "services": {"streamlit", "pandas"},
}


def iter_python_files(layer: str) -> List[str]:
    base = os.path.join(ROOT, layer)
    if not os.path.isdir(base):
        return []
    files = []
    for dirpath, _dirnames, filenames in os.walk(base):
        if "__pycache__" in dirpath:
            continue
        for name in filenames:
            if name.endswith(".py"):
                files.append(os.path.join(dirpath, name))
    return sorted(files)


def imports_of(path: str) -> Set[str]:
    """文件中出现的所有绝对模块名（含 ``from x import y`` 的 x）。"""
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        print(f"[语法错误] {path}: {exc}")
        return set()

    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对导入：视为本层内部
                continue
            if node.module:
                found.add(node.module)
    return found


def top_level(module: str) -> str:
    return module.split(".")[0]


BASELINE_FILE = os.path.join(ROOT, "scripts", "layer_baseline.txt")


def load_baseline() -> Set[tuple]:
    """读取已知债务清单：每行 ``相对路径\t导入模块``。

    存量代码里确实存在反向依赖（例如数据层引用业务层的状态机），这些
    不该拦住本次改动，但必须被计数。基线只「记账」，不「赦免」：一旦
    某条被修好，下次体检会提示把它从基线里删掉。
    """
    known: Set[tuple] = set()
    if not os.path.exists(BASELINE_FILE):
        return known
    with open(BASELINE_FILE, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) == 2:
                known.add((parts[0].strip(), parts[1].strip()))
    return known


def check(verbose: bool = False) -> int:
    baseline = load_baseline()
    fresh: List[str] = []
    legacy: List[str] = []
    summary: List[str] = []
    hits: Set[tuple] = set()

    for layer, allowed in ALLOWED.items():
        files = iter_python_files(layer)
        if not files:
            continue
        internal: Set[str] = set()
        for path in files:
            relpath = os.path.relpath(path, ROOT)
            for module in imports_of(path):
                head = top_level(module)
                if head not in PROJECT_PACKAGES:
                    if head in EXTRA_FORBIDDEN.get(layer, set()):
                        hit = (relpath, module)
                        hits.add(hit)
                        text = f"{relpath} 导入了 {module}（{layer} 层禁止）"
                        (legacy if hit in baseline else fresh).append(text)
                    continue
                internal.add(head)
                if head in allowed:
                    continue
                hit = (relpath, module)
                hits.add(hit)
                text = (
                    f"{relpath} 导入了 {module}"
                    f"（{layer} 层只允许 {sorted(allowed)}）"
                )
                (legacy if hit in baseline else fresh).append(text)
        summary.append(f"{layer:12s} {len(files):3d} 文件，依赖 {sorted(internal)}")

    print("分层依赖体检")
    print("-" * 68)
    for line in summary:
        print("  " + line)
    print("-" * 68)

    if legacy:
        print(f"既有债务 {len(legacy)} 处（已入基线，不阻断）：")
        for item in legacy:
            print("  · " + item)

    stale = baseline - hits
    if stale:
        print(f"基线中已不再出现的条目 {len(stale)} 条，可考虑删除：")
        for relpath, module in sorted(stale):
            print(f"  · {relpath}\t{module}")

    if fresh:
        print(f"新增违规 {len(fresh)} 处：")
        for item in fresh:
            print("  ✗ " + item)
        return 1

    print("通过：本次改动未引入新的依赖违规")
    if verbose:
        print("\n规则：")
        for layer, allowed in ALLOWED.items():
            print(f"  {layer:12s} 可用 → {sorted(allowed)}")
    return 0


if __name__ == "__main__":
    sys.exit(check(verbose="-v" in sys.argv))
