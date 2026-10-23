"""瓶身二维码载荷单元测试（utils/qr_label.py）。

码里放什么，决定了手机扫一下之后是「直接进页面」还是「还得再扫一次」。
这里测的是三种内容格式的互认，以及一条现实约束：**配了地址和没配地址
生成的码必须都能被 parse 认出来**——标签贴上去要用两年，而服务器地址
半年就可能变一次，两种码会同时存在于同一个货架上。
"""
import unittest

from utils.qr_label import (
    BOTTLE_PARAM,
    GOOD_MODULE_MM,
    SHORT_PREFIX,
    fit,
    label_png,
    parse,
    payload_of,
    png_bytes,
)

BOTTLE = "B-20261023-001"


class TestPayload(unittest.TestCase):
    def test_url_payload_when_base_configured(self):
        payload = payload_of(BOTTLE, "http://192.168.1.10:8601")
        self.assertEqual(payload, f"http://192.168.1.10:8601/m?{BOTTLE_PARAM}={BOTTLE}")

    def test_base_url_trailing_slash_is_trimmed(self):
        """多一个斜杠会出现 //m，某些手机会当成协议相对地址。"""
        payload = payload_of(BOTTLE, "http://192.168.1.10:8601/")
        self.assertNotIn("//m", payload.replace("http://", ""))

    def test_short_payload_without_base(self):
        self.assertEqual(payload_of(BOTTLE), SHORT_PREFIX + BOTTLE)

    def test_empty_bottle_gives_empty_payload(self):
        self.assertEqual(payload_of(""), "")
        self.assertEqual(payload_of("   "), "")


class TestParse(unittest.TestCase):
    def test_parse_short_code(self):
        self.assertEqual(parse(SHORT_PREFIX + BOTTLE), BOTTLE)

    def test_parse_url(self):
        self.assertEqual(
            parse(f"http://192.168.1.10:8601/m?{BOTTLE_PARAM}={BOTTLE}"), BOTTLE
        )

    def test_parse_url_with_other_params(self):
        """URL 里混了别的参数也能取出瓶号。"""
        self.assertEqual(
            parse(f"http://host:8601/m?from=qr&{BOTTLE_PARAM}={BOTTLE}&x=1"), BOTTLE
        )

    def test_parse_url_without_bottle_returns_none(self):
        """光一个 /m 不算扫到瓶子。"""
        self.assertIsNone(parse("http://host:8601/m"))
        self.assertIsNone(parse("http://host:8601/m?other=1"))

    def test_parse_raw_number(self):
        """裸瓶号也认——有人直接拿瓶号生成码，或者手工输进来。"""
        self.assertEqual(parse(BOTTLE), BOTTLE)

    def test_parse_empty(self):
        self.assertIsNone(parse(""))
        self.assertIsNone(parse("   "))

    def test_roundtrip_both_forms(self):
        for payload in (payload_of(BOTTLE, "http://10.0.0.2:8601"), payload_of(BOTTLE)):
            self.assertEqual(parse(payload), BOTTLE)


class TestFit(unittest.TestCase):
    """容量这件事只在「印多大」这个前提下有意义。

    版本 40 能装 2953 字节，但那是 177 个模块，19.5 mm 标签上每模块
    0.11 mm —— 扫不出来。所以这里测的是模块边长这条硬约束。
    """

    def test_short_code_is_comfortable(self):
        """短码（22 字节）在小瓶标签上每模块 ≥0.45 mm。"""
        info = fit(payload_of(BOTTLE))
        self.assertEqual(info.grade, "good")
        self.assertGreaterEqual(info.module_mm, GOOD_MODULE_MM)

    def test_url_is_still_ok_at_label_size(self):
        """一条普通内网 URL（48 字节）仍在舒适区。"""
        info = fit(payload_of(BOTTLE, "http://192.168.1.10:8601"))
        self.assertTrue(info.readable)
        self.assertLess(info.version, 8)

    def test_long_payload_gets_denser(self):
        """内容越长版本越高、模块越小——这就是「容量」的真实代价。"""
        short = fit("a" * 20)
        long = fit("a" * 200)
        self.assertGreater(long.version, short.version)
        self.assertLess(long.module_mm, short.module_mm)

    def test_absurd_payload_is_reported_hopeless(self):
        info = fit("a" * 1200)
        self.assertEqual(info.grade, "too_small")
        self.assertFalse(info.readable)

    def test_bigger_label_restores_readability(self):
        """同一段内容，把标签打大就又能扫了——所以提示里两条建议都成立。"""
        payload = "a" * 200
        self.assertNotEqual(fit(payload, code_mm=19.5).grade, "good")
        self.assertEqual(fit(payload, code_mm=60.0).grade, "good")

    def test_empty_payload_has_no_fit(self):
        self.assertIsNone(fit(""))


class TestRender(unittest.TestCase):
    def test_png_bytes_are_png(self):
        data = png_bytes(payload_of(BOTTLE))
        self.assertIsNotNone(data)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_empty_payload_gives_none(self):
        self.assertIsNone(png_bytes(""))

    def test_label_is_a_png(self):
        data = label_png(BOTTLE, extra="乙醇")
        self.assertIsNotNone(data)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
