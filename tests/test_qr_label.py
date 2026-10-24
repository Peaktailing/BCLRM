"""瓶身二维码载荷单元测试（utils/qr_label.py）。

码里放什么，决定了手机扫一下之后是「直接进页面」还是「还得再扫一次」。
这里测的是三种内容格式的互认（v2 短码 / v1 老短码 / URL），以及一条现实
约束：**配了地址和没配地址生成的码必须都能被解析**——标签贴上去要用两年，
而服务器地址半年就可能变一次，两种码会同时存在于同一个货架上。

另外测一条容量约束：带上 CAS 与入库日期后码变密了（20 → 39 字节），
但 19.5 mm 标签上每模块仍有 0.6 mm，仍在「一扫即中」的区间。
"""
import unittest

from utils.qr_label import (
    BOTTLE_PARAM,
    FIELD_SEP,
    GOOD_MODULE_MM,
    LONG_PREFIX,
    MOBILE_PATH,
    SHORT_PREFIX,
    fit,
    label_png,
    parse,
    parse_fields,
    payload_of,
    png_bytes,
)

#: 实际瓶号格式：``YYYYMMDD`` + 4 位当日序号（12 位数字）。
BOTTLE = "202610230001"
CAS = "64-17-5"
DAY = "2026-10-23"


class TestPayload(unittest.TestCase):
    def test_url_payload_when_base_configured(self):
        payload = payload_of(BOTTLE, "http://192.168.1.10:8601")
        self.assertEqual(
            payload, f"http://192.168.1.10:8601{MOBILE_PATH}?{BOTTLE_PARAM}={BOTTLE}"
        )

    def test_base_url_trailing_slash_is_trimmed(self):
        """多一个斜杠会出现 //m，某些手机会当成协议相对地址。"""
        payload = payload_of(BOTTLE, "http://192.168.1.10:8601/")
        self.assertNotIn("//m", payload.replace("http://", ""))

    def test_url_does_not_carry_cas_or_date(self):
        """URL 的前提是能联网，联网就该问系统，别让码替系统记档案。"""
        payload = payload_of(BOTTLE, "http://h:8601", CAS, DAY)
        self.assertNotIn(CAS, payload)
        self.assertNotIn(DAY, payload)

    def test_short_payload_without_base(self):
        self.assertEqual(payload_of(BOTTLE), LONG_PREFIX + BOTTLE)

    def test_short_payload_carries_three_fields(self):
        self.assertEqual(
            payload_of(BOTTLE, cas=CAS, inbound_date=DAY),
            f"{LONG_PREFIX}{BOTTLE}{FIELD_SEP}{CAS}{FIELD_SEP}{DAY}",
        )

    def test_missing_cas_keeps_the_slot(self):
        """CAS 空着也要占位——省掉位置会把日期读成 CAS。"""
        self.assertEqual(
            payload_of(BOTTLE, cas="", inbound_date=DAY),
            f"{LONG_PREFIX}{BOTTLE}{FIELD_SEP}{FIELD_SEP}{DAY}",
        )

    def test_missing_date_trims_the_tail(self):
        self.assertEqual(
            payload_of(BOTTLE, cas=CAS, inbound_date=""),
            f"{LONG_PREFIX}{BOTTLE}{FIELD_SEP}{CAS}",
        )

    def test_empty_bottle_gives_empty_payload(self):
        self.assertEqual(payload_of(""), "")
        self.assertEqual(payload_of("   "), "")


class TestParse(unittest.TestCase):
    def test_parse_v2_full(self):
        self.assertEqual(parse(payload_of(BOTTLE, cas=CAS, inbound_date=DAY)), BOTTLE)

    def test_parse_fields_returns_all_three(self):
        fields = parse_fields(payload_of(BOTTLE, cas=CAS, inbound_date=DAY))
        self.assertEqual(fields, {"bottle": BOTTLE, "cas": CAS, "inbound": DAY})

    def test_parse_fields_with_missing_cas(self):
        fields = parse_fields(payload_of(BOTTLE, inbound_date=DAY))
        self.assertEqual(fields["bottle"], BOTTLE)
        self.assertEqual(fields["cas"], "")
        self.assertEqual(fields["inbound"], DAY)

    def test_parse_v1_legacy_short_code(self):
        """老标签（v1 短码）必须还能扫——贴上去两年了，不能说换格式就废。"""
        self.assertEqual(parse(SHORT_PREFIX + BOTTLE), BOTTLE)
        self.assertEqual(
            parse_fields(SHORT_PREFIX + BOTTLE),
            {"bottle": BOTTLE, "cas": "", "inbound": ""},
        )

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
        self.assertIsNone(parse(LONG_PREFIX))
        self.assertEqual(parse_fields(""), {})

    def test_roundtrip_three_forms(self):
        payloads = (
            payload_of(BOTTLE, "http://10.0.0.2:8601"),
            payload_of(BOTTLE),
            payload_of(BOTTLE, cas=CAS, inbound_date=DAY),
        )
        for payload in payloads:
            self.assertEqual(parse(payload), BOTTLE)


class TestFit(unittest.TestCase):
    """容量这件事只在「印多大」这个前提下有意义。

    版本 40 能装 2953 字节，但那是 177 个模块，19.5 mm 标签上每模块
    0.11 mm —— 扫不出来。所以这里测的是模块边长这条硬约束。
    """

    def test_short_code_is_comfortable(self):
        """只有瓶号的短码（20 字节）在小瓶标签上每模块 ≥0.45 mm。"""
        info = fit(payload_of(BOTTLE))
        self.assertEqual(info.grade, "good")
        self.assertGreaterEqual(info.module_mm, GOOD_MODULE_MM)

    def test_three_fields_still_fit_a_small_bottle(self):
        """瓶号 + CAS + 入库日期（39 字节）只到版本 3，仍是舒适区。

        v3 是刻意守住的边界：一旦超过 50 字节就跳到 v4，每模块 0.56 mm，
        再往上加字段（效期、规格）就会把标签推到「要凑近才扫得稳」。
        """
        info = fit(payload_of(BOTTLE, cas=CAS, inbound_date=DAY))
        self.assertEqual(info.grade, "good")
        self.assertLessEqual(info.version, 4)
        self.assertGreaterEqual(info.module_mm, GOOD_MODULE_MM)
        # 比只有瓶号时密，但没有密到另一个量级
        self.assertGreater(info.payload_bytes, fit(payload_of(BOTTLE)).payload_bytes)

    def test_url_is_still_ok_at_label_size(self):
        """一条普通内网 URL（≈46 字节）仍在舒适区。"""
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
        data = png_bytes(payload_of(BOTTLE, cas=CAS, inbound_date=DAY))
        self.assertIsNotNone(data)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_empty_payload_gives_none(self):
        self.assertIsNone(png_bytes(""))

    def test_label_is_a_png(self):
        data = label_png(BOTTLE, extra="乙醇")
        self.assertIsNotNone(data)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_label_with_cas_and_date(self):
        """CAS 与入库日期既进码也印成字——瓶子拿下来那刻没人先掏手机。"""
        data = label_png(
            BOTTLE,
            extra="乙醇",
            cas=CAS,
            inbound_date=DAY,
            payload=payload_of(BOTTLE, cas=CAS, inbound_date=DAY),
        )
        self.assertIsNotNone(data)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_label_survives_missing_optional_fields(self):
        data = label_png(BOTTLE)
        self.assertIsNotNone(data)


if __name__ == "__main__":
    unittest.main()
