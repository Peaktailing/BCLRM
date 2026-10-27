"""手册裁剪纯函数测试：手机取证章节按开关隐藏，其余内容不动。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.manual_filter import hide_mobile_sections


SAMPLE = """# 手册

| 导航项 | 描述 |
|--------|------|
| 🏠 首页 | 概览 |
| 📷 手机取证 | 扫码拍照 |

### 3.13 其他页面

正文 A。

### 3.14 手机取证

手机扫码后拍照。

#### 3.14.1 子标题

子节内容。

### 3.15 另一个页面

正文 B。
"""


class TestHideMobileSections(unittest.TestCase):
    def test_removes_table_row_and_section(self):
        text = hide_mobile_sections(SAMPLE)
        self.assertNotIn("手机取证", text)
        self.assertNotIn("手机扫码后拍照", text)
        self.assertNotIn("子节内容", text, "同节子标题内容必须一起藏掉")

    def test_keeps_neighbouring_sections(self):
        text = hide_mobile_sections(SAMPLE)
        self.assertIn("3.13 其他页面", text)
        self.assertIn("正文 A。", text)
        self.assertIn("3.15 另一个页面", text)
        self.assertIn("正文 B。", text)

    def test_empty_input_passthrough(self):
        self.assertEqual(hide_mobile_sections(""), "")
        plain = "# 标题\n\n没有手机功能。"
        self.assertEqual(hide_mobile_sections(plain), plain)


if __name__ == "__main__":
    unittest.main()
