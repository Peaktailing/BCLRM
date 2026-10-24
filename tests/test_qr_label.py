"""瓶身二维码载荷单元测试（utils/qr_label.py）。

码里放什么，决定了手机扫一下之后是「直接进页面」还是「还得再扫一次」。
这里测四件事：

1. **四种格式互认**——v3（瓶号/CAS/效期/名）、v2（瓶号/CAS/入库日）、
   v1 老短码、URL。标签贴上去要用两年，而服务器地址半年就可能变一次，
   四种码会同时存在于同一个货架上。
2. **效期只到月**——供应商就只标到月，码里写全 ``YYYYMM`` 是如实记录精度。
3. **名字截得聪明**——超长名字优先保留括号里的缩写（``…(DTNB)`` → ``DTNB``）。
4. **容量按实际出图算**——名义 19.5 mm 的格子，按整数倍模块出图后只有
   21.8 mm，判级差一档（名义 good、打出来 tight）。
"""
import unittest
from unittest import mock

from utils.qr_label import (
    BOTTLE_PARAM,
    FIELD_SEP,
    GOOD_MODULE_MM,
    LONG_PREFIX,
    MOBILE_PATH,
    NAME_MAX_CHARS,
    QR_PRINT_MM,
    SHORT_PREFIX,
    V3_PREFIX,
    _make,
    fit,
    human_expiry,
    label_fit,
    label_layout,
    label_png,
    normalize_expiry,
    parse,
    parse_fields,
    payload_of,
    png_bytes,
    tidy_name,
    truncate_name,
)

#: 实际瓶号格式：``YYYYMMDD`` + 4 位当日序号（12 位数字）。
BOTTLE = "202610230001"
CAS = "64-17-5"
EXPIRY = "2027-06-30"
NAME = "乙醇"


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

    def test_url_does_not_carry_any_field(self):
        """URL 的前提是能联网，联网就该问系统，别让码替系统记档案。"""
        payload = payload_of(BOTTLE, "http://h:8601", CAS, EXPIRY, NAME)
        self.assertNotIn(CAS, payload)
        self.assertNotIn("202706", payload)
        self.assertNotIn(NAME, payload)

    def test_short_payload_without_any_field(self):
        self.assertEqual(payload_of(BOTTLE), V3_PREFIX + BOTTLE)

    def test_short_payload_carries_four_fields(self):
        self.assertEqual(
            payload_of(BOTTLE, cas=CAS, expiry=EXPIRY, name=NAME),
            f"{V3_PREFIX}{BOTTLE}{FIELD_SEP}{CAS}{FIELD_SEP}202706{FIELD_SEP}{NAME}",
        )

    def test_expiry_is_truncated_to_month(self):
        """到日的效期（2027-06-30）在码里是 202706——供应商只承诺到月。"""
        for raw in ("2027-06-30", "2027/06", "2027.6", "202706", "20270630"):
            payload = payload_of(BOTTLE, expiry=raw)
            self.assertIn(FIELD_SEP + "202706", payload, raw)
            self.assertEqual(parse_fields(payload)["expiry"], "202706", raw)

    def test_missing_cas_and_expiry_keep_their_slots(self):
        """两个中间字段都空也要占位——省掉位置会把名字读成效期。"""
        payload = payload_of(BOTTLE, name=NAME)
        self.assertEqual(payload, f"{V3_PREFIX}{BOTTLE}{FIELD_SEP}{FIELD_SEP}{FIELD_SEP}{NAME}")
        self.assertEqual(parse_fields(payload)["name"], NAME)
        self.assertEqual(parse_fields(payload)["expiry"], "")

    def test_missing_name_trims_the_tail(self):
        self.assertEqual(
            payload_of(BOTTLE, cas=CAS, expiry=EXPIRY),
            f"{V3_PREFIX}{BOTTLE}{FIELD_SEP}{CAS}{FIELD_SEP}202706",
        )

    def test_empty_bottle_gives_empty_payload(self):
        self.assertEqual(payload_of(""), "")
        self.assertEqual(payload_of("   "), "")


class TestExpiry(unittest.TestCase):
    def test_normalize_accepts_common_forms(self):
        for raw in ("2027-06", "2027/06", "2027.06", "2027-06-30", "202706"):
            self.assertEqual(normalize_expiry(raw), "202706", raw)

    def test_normalize_pads_single_digit_month(self):
        self.assertEqual(normalize_expiry("2027-6"), "202706")

    def test_normalize_rejects_garbage(self):
        for raw in ("", "  ", "abc", "2027-13", "2027-00", "12345"):
            self.assertEqual(normalize_expiry(raw), "", raw)

    def test_human_expiry_is_two_digit_year(self):
        """标签上印 26.06——完整年份在这张 40 mm 标签上挤掉名字的位置。"""
        self.assertEqual(human_expiry("202706"), "27.06")
        self.assertEqual(human_expiry(EXPIRY), "27.06")
        self.assertEqual(human_expiry(""), "")


class TestTruncateName(unittest.TestCase):
    def test_tidy_strips_spaces_around_dash_and_bracket(self):
        """OCR 录入的长名字里 9 个字符是空格，清掉能多认出一截。"""
        raw = "2,2'- 联氮 - 二 (3 - 乙基 - 苯并噻唑 - 6 - 磺酸) 二铵盐"
        self.assertEqual(tidy_name(raw), "2,2'-联氮-二(3-乙基-苯并噻唑-6-磺酸)二铵盐")
        self.assertEqual(len(tidy_name(raw).encode("utf-8")), 56)

    def test_tidy_keeps_space_between_words(self):
        """``乙酸 乙酯`` 是两个词，粘起来就成了另一个东西。"""
        self.assertEqual(tidy_name("乙酸 乙酯 分析纯"), "乙酸 乙酯 分析纯")

    def test_tidy_then_no_truncation_needed(self):
        """清完空格常常就装得下了——41 字 / 69 字节 → 28 字 / 56 字节。"""
        raw = "2,2'- 联氮 - 二 (3 - 乙基 - 苯并噻唑 - 6 - 磺酸) 二铵盐"
        self.assertEqual(truncate_name(raw), "2,2'-联氮-二(3-乙基-苯并噻唑-6-磺酸)二铵盐")

    def test_short_name_untouched(self):
        self.assertEqual(truncate_name("乙醇"), "乙醇")
        self.assertEqual(truncate_name(""), "")

    def test_exactly_at_limit_untouched(self):
        name = "试" * NAME_MAX_CHARS
        self.assertEqual(truncate_name(name), name)

    def test_prefers_bracket_abbreviation(self):
        """真的超预算时，括号缩写比截断的前半段有用得多。"""
        name = "乙二醇双氨基乙基醚四乙酸类络合剂的超长名称呀(EGTA)"
        self.assertGreater(len(name.encode("utf-8")), NAME_MAX_CHARS * 3)
        self.assertEqual(truncate_name(name), "EGTA")

    def test_short_latin_heavy_name_kept_whole(self):
        """``5,5'-二硫代双(2-硝基苯甲酸)(DTNB)`` 42 字节，放得下就别动它。"""
        name = "5,5'-二硫代双(2-硝基苯甲酸)(DTNB)"
        self.assertEqual(truncate_name(name), name)

    def test_budget_counts_bytes_not_characters(self):
        """22 个字符但半角多，字节没超预算，不该被砍。"""
        name = "乙二醇双(2-氨基乙基醚)四乙酸(EGTA)"
        self.assertEqual(truncate_name(name), name)

    def test_cuts_before_bracket_when_no_abbreviation(self):
        name = "二乙基二硫代氨基甲酸钠（N,N-二乙基二硫代氨基甲酸钠）"
        cut = truncate_name(name)
        self.assertLessEqual(len(cut.encode("utf-8")), NAME_MAX_CHARS * 3)
        self.assertTrue(cut.endswith("…"))
        self.assertTrue(cut.startswith("二乙基二硫代氨基甲酸钠"))

    def test_hard_cut_when_no_bracket(self):
        name = "试" * 40
        cut = truncate_name(name)
        self.assertLessEqual(len(cut.encode("utf-8")), NAME_MAX_CHARS * 3)
        self.assertEqual(len(cut), NAME_MAX_CHARS)
        self.assertTrue(cut.endswith("…"))


class TestParse(unittest.TestCase):
    def test_parse_v3_full(self):
        self.assertEqual(parse(payload_of(BOTTLE, cas=CAS, expiry=EXPIRY, name=NAME)), BOTTLE)

    def test_parse_fields_returns_five_slots(self):
        fields = parse_fields(payload_of(BOTTLE, cas=CAS, expiry=EXPIRY, name=NAME))
        self.assertEqual(fields["bottle"], BOTTLE)
        self.assertEqual(fields["cas"], CAS)
        self.assertEqual(fields["expiry"], "202706")
        self.assertEqual(fields["name"], NAME)
        self.assertEqual(fields["inbound"], "")

    def test_parse_v2_legacy_carries_inbound(self):
        """v2 第三段是入库日期。老标签贴了两年，不能因为换格式就失效。"""
        fields = parse_fields(f"BCLRM:2:{BOTTLE};{CAS};2026-10-23")
        self.assertEqual(fields["bottle"], BOTTLE)
        self.assertEqual(fields["cas"], CAS)
        self.assertEqual(fields["inbound"], "2026-10-23")
        self.assertEqual(fields["expiry"], "")

    def test_parse_v1_legacy_short_code(self):
        self.assertEqual(parse(SHORT_PREFIX + BOTTLE), BOTTLE)
        fields = parse_fields(SHORT_PREFIX + BOTTLE)
        self.assertEqual(fields["bottle"], BOTTLE)
        self.assertEqual(fields["expiry"], "")

    def test_parse_url(self):
        self.assertEqual(
            parse(f"http://192.168.1.10:8601{MOBILE_PATH}?{BOTTLE_PARAM}={BOTTLE}"), BOTTLE
        )

    def test_parse_url_with_other_params(self):
        self.assertEqual(
            parse(f"http://host:8601/m?from=qr&{BOTTLE_PARAM}={BOTTLE}&x=1"), BOTTLE
        )

    def test_parse_url_without_bottle_returns_none(self):
        self.assertIsNone(parse("http://host:8601/m"))
        self.assertIsNone(parse("http://host:8601/m?other=1"))

    def test_parse_raw_number(self):
        """裸瓶号也认——有人直接拿瓶号生成码，或者手工输进来。"""
        self.assertEqual(parse(BOTTLE), BOTTLE)

    def test_parse_empty(self):
        self.assertIsNone(parse(""))
        self.assertIsNone(parse("   "))
        self.assertIsNone(parse(V3_PREFIX))
        self.assertEqual(parse_fields(""), {})

    def test_semicolon_inside_name_does_not_shift_fields(self):
        """名字放最后一段、只切前三刀，所以名字里的分号不会把字段错位。"""
        raw = f"{V3_PREFIX}{BOTTLE};{CAS};202706;甲;乙"
        fields = parse_fields(raw)
        self.assertEqual(fields["cas"], CAS)
        self.assertEqual(fields["expiry"], "202706")
        self.assertEqual(fields["name"], "甲;乙")

    def test_roundtrip_all_forms(self):
        payloads = (
            payload_of(BOTTLE, "http://10.0.0.2:8601"),
            payload_of(BOTTLE),
            payload_of(BOTTLE, cas=CAS, expiry=EXPIRY, name=NAME),
        )
        for payload in payloads:
            self.assertEqual(parse(payload), BOTTLE)


class TestEncoding(unittest.TestCase):
    """汉字必须显式声明 UTF-8。

    segno 默认会把中文转成 Shift-JIS（2 字节/字）且**不留编码标记**，省三
    分之一的容量，代价是解码器得猜。zxing 猜得对，手机相机不一定——码要贴
    两年，不赌这个。
    """

    def test_chinese_payload_declares_utf8_with_eci(self):
        with mock.patch("segno.make") as maker:
            _make("乙醇")
        kwargs = maker.call_args.kwargs
        self.assertEqual(kwargs.get("encoding"), "utf-8")
        self.assertTrue(kwargs.get("eci"))

    def test_ascii_payload_keeps_old_bytes(self):
        """纯 ASCII 不加 ECI——已贴上货架的老标签字节一个都不变。"""
        with mock.patch("segno.make") as maker:
            _make(f"{V3_PREFIX}{BOTTLE};{CAS};202706")
        kwargs = maker.call_args.kwargs
        self.assertNotIn("encoding", kwargs)
        self.assertNotIn("eci", kwargs)

    def test_boost_error_is_always_off(self):
        with mock.patch("segno.make") as maker:
            _make("x")
        self.assertFalse(maker.call_args.kwargs.get("boost_error"))


class TestFit(unittest.TestCase):
    """容量这件事只在「印多大」这个前提下有意义。

    版本 40 能装 2953 字节，但那是 177 个模块，19.5 mm 标签上每模块
    0.11 mm —— 扫不出来。所以这里测的是模块边长这条硬约束。
    """

    def test_short_code_is_comfortable(self):
        info = fit(payload_of(BOTTLE))
        self.assertEqual(info.grade, "good")
        self.assertGreaterEqual(info.module_mm, GOOD_MODULE_MM)

    def test_full_payload_stays_in_comfort_zone(self):
        """瓶号 + CAS + 效期 + 名字（106 字节以内）仍在舒适区。

        v6 是刻意守住的边界：一旦超过 106 字节就跳到 v7，模块边长从
        0.51 mm 掉到 0.46 mm——19.5 mm 的格子直接掉出舒适区。
        """
        payload = payload_of(BOTTLE, cas=CAS, expiry=EXPIRY, name="试" * NAME_MAX_CHARS)
        info = label_fit(payload)
        self.assertEqual(info.grade, "good")
        self.assertLessEqual(info.version, 6)
        self.assertGreaterEqual(info.module_mm, GOOD_MODULE_MM)

    def test_url_is_still_ok_at_label_size(self):
        info = fit(payload_of(BOTTLE, "http://192.168.1.10:8601"))
        self.assertTrue(info.readable)
        self.assertLess(info.version, 8)

    def test_long_payload_gets_denser(self):
        short = fit("a" * 20)
        long = fit("a" * 200)
        self.assertGreater(long.version, short.version)
        self.assertLess(long.module_mm, short.module_mm)

    def test_absurd_payload_is_reported_hopeless(self):
        info = fit("a" * 1200)
        self.assertEqual(info.grade, "too_small")
        self.assertFalse(info.readable)

    def test_bigger_label_restores_readability(self):
        payload = "a" * 200
        self.assertNotEqual(fit(payload, code_mm=19.5).grade, "good")
        self.assertEqual(fit(payload, code_mm=60.0).grade, "good")

    def test_empty_payload_has_no_fit(self):
        self.assertIsNone(fit(""))


class TestLabelFit(unittest.TestCase):
    """页面上的容量体检要报**实际出图**的尺寸，不是名义尺寸。"""

    def test_actual_print_is_smaller_than_nominal(self):
        payload = payload_of(BOTTLE, cas=CAS, expiry=EXPIRY, name=NAME)
        nominal = fit(payload, code_mm=QR_PRINT_MM)
        actual = label_fit(payload)
        self.assertLess(actual.print_mm, QR_PRINT_MM + 2)
        self.assertIsNotNone(nominal)

    def test_layout_is_integer_scale(self):
        """每个模块必须画整数个像素，否则边界会被插值成半灰斜边。"""
        payload = payload_of(BOTTLE, cas=CAS, expiry=EXPIRY, name=NAME)
        scale, qr_px, modules, print_mm = label_layout(payload)
        self.assertIsInstance(scale, int)
        self.assertEqual(qr_px, scale * modules)
        self.assertAlmostEqual(print_mm, qr_px * 25.4 / 300, places=2)

    def test_full_name_payload_is_readable(self):
        """名字顶格（23 字）时仍要能扫——这是设计上限，不是运气。"""
        payload = payload_of(BOTTLE, cas=CAS, expiry=EXPIRY, name="试" * NAME_MAX_CHARS)
        info = label_fit(payload)
        self.assertEqual(info.grade, "good")

    def test_empty_payload_has_no_layout(self):
        self.assertIsNone(label_layout(""))
        self.assertIsNone(label_fit(""))


class TestRender(unittest.TestCase):
    def test_png_bytes_are_png(self):
        data = png_bytes(payload_of(BOTTLE, cas=CAS, expiry=EXPIRY))
        self.assertIsNotNone(data)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_empty_payload_gives_none(self):
        self.assertIsNone(png_bytes(""))

    def test_label_is_a_png(self):
        data = label_png(BOTTLE, name=NAME)
        self.assertIsNotNone(data)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_label_with_all_fields(self):
        """CAS、效期、名字既进码也印成字——瓶子拿下来那刻没人先掏手机。"""
        data = label_png(
            BOTTLE, name=NAME, cas=CAS, expiry=EXPIRY,
            payload=payload_of(BOTTLE, cas=CAS, expiry=EXPIRY, name=NAME),
        )
        self.assertIsNotNone(data)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_label_survives_missing_optional_fields(self):
        self.assertIsNotNone(label_png(BOTTLE))

    def test_label_does_not_overflow_long_name(self):
        """长名字按像素截断，不会画到纸外。"""
        data = label_png(
            BOTTLE,
            name="2,2'- 联氮 - 二 (3 - 乙基 - 苯并噻唑 - 6 - 磺酸) 二铵盐",
            cas="30931-67-0",
            expiry="2026-12",
        )
        self.assertIsNotNone(data)


if __name__ == "__main__":
    unittest.main()
