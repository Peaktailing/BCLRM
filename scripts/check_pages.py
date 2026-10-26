"""页面渲染体检：用 AppTest 把每个页面跑一遍，只看「有没有炸」。

``scripts/check_layers.py`` 管依赖方向，``scripts/check_consistency.py`` 管账,
这个脚本管**页面还能不能打开**。Streamlit 的页面不会被单元测试自然覆盖：改了
服务层的返回结构、少传一个参数，测试可能全绿，页面一打开就红屏。所以单独跑
一遍，用退出码当门禁。

用法::

    TMPDIR=/tmp python scripts/check_pages.py            # 全部页面
    TMPDIR=/tmp python scripts/check_pages.py 16 15      # 只跑编号前缀

退出码：0 = 全部无异常；1 = 至少一个页面抛异常。
"""
from __future__ import annotations

import os
import sys
import time
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

VIEWS_DIR = os.path.join(PROJECT_ROOT, "views")

#: 登录态的最小集合。缺一个页面就会停在登录表单上，体检等于没做。
SESSION = {
    "logged_in": True,
    "user_name": "体检账号",
    "user_role": "admin",
    "is_admin": True,
    "must_change_password": False,
}


def view_files(prefixes=None):
    names = sorted(
        name
        for name in os.listdir(VIEWS_DIR)
        if name.endswith(".py") and not name.startswith("__")
    )
    if prefixes:
        names = [name for name in names if name.split("_")[0] in prefixes]
    return names


#: ``st.page_link`` 在 AppTest 里必然失败：它要求页面先由 ``st.Page`` 注册，
#: 而体检是**独立运行单个文件**，没有入口也就没有导航表。这不是页面写错了，
#: 所以按「跳过」处理——否则每个带跳转按钮的页面都会假装坏掉。
_LINK_ERROR = "StreamlitPageNotFoundError"


def _is_page_link_only(error) -> bool:
    stack = "\n".join(getattr(error, "stack_trace", []) or [])
    return "st.page_link(" in stack or _LINK_ERROR in stack


def check(name: str) -> int:
    """跑一个页面，返回**真异常**个数（page_link 跳过的不算）。"""
    path = os.path.join(VIEWS_DIR, name)
    tester = AppTest.from_file(path, default_timeout=120)
    for key, value in SESSION.items():
        tester.session_state[key] = value
    tester.session_state["last_activity"] = time.time()
    tester.run()
    errors = list(tester.exception)
    real = [error for error in errors if not _is_page_link_only(error)]
    skipped = len(errors) - len(real)
    flag = "OK " if not real else "ERR"
    note = f"  (跳过 page_link {skipped} 处)" if skipped else ""
    print(f"[{flag}] {name}  exception={len(real)} button={len(tester.button)}{note}")
    for error in real[:3]:
        print(f"        !! {error.message}")
        for line in (getattr(error, "stack_trace", []) or [])[-2:]:
            print(f"           {line.strip().splitlines()[-1]}")
    return len(real)


def main(argv) -> int:
    prefixes = set(argv[1:]) or None
    files = view_files(prefixes)
    if not files:
        print("没有匹配的页面文件")
        return 1
    total = 0
    bad = 0
    for name in files:
        try:
            count = check(name)
        except Exception:  # noqa: BLE001 - 体检脚本自己不能把门禁带崩
            traceback.print_exc()
            count = 1
        total += count
        bad += 1 if count else 0
    print(f"\n共 {len(files)} 个页面，异常页 {bad} 个，异常 {total} 处")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
