"""现场取证单元测试（business/evidence_service.py）。

测的是「一张照片挂在哪、能不能被找到、必拍会不会被绕过」这三件事。
拍照本身没法测，但账能测：

1. **挂载键** —— 照片挂在工单号上，两个阶段互不覆盖。挂错地方，事后查单
   就找不到，等于没拍。
2. **必拍是开关** —— 开关关了必须放行，开着必须拦住。页面和服务端看的是
   同一个值，否则会出现「显示必填但能提交」。
3. **压缩失败不丢证据** —— 一张处理不了的照片仍然要留下来。
"""
import io
import unittest
import tempfile

from PIL import Image

from business.evidence_service import (
    PHASE_BORROW,
    PHASE_RETURN,
    REF_TYPE_ORDER,
    EvidenceService,
)
from services.base.attachment_index_service import attachment_index_service
from services.base.system_config_service import EvidenceConfig, system_config_service
from utils.attachment_store import AttachmentStore

ORDER = "BO20261023143000001"
ORDER_2 = "BO20261023150000002"


class _FakeUpload:
    """模拟 Streamlit UploadedFile（只需 name 与 getvalue()）。"""

    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


def _photo_bytes(size=(2400, 1800)) -> bytes:
    image = Image.new("RGB", size, (120, 160, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = AttachmentStore(base_dir=self._tmp.name)
        self.service = EvidenceService(
            store=self.store, config=system_config_service
        )
        self._clear()
        # 默认：两个阶段都必拍
        system_config_service.set(EvidenceConfig.REQUIRE_BORROW, "1", "test")
        system_config_service.set(EvidenceConfig.REQUIRE_RETURN, "1", "test")

    def tearDown(self):
        self._clear()
        self._tmp.cleanup()

    @staticmethod
    def _clear():
        try:
            attachment_index_service.db.execute_update("DELETE FROM attachment_index")
        except Exception:
            pass


class TestAttach(_Base):
    def test_photo_is_saved_and_indexed(self):
        """落盘 + 索引登记，两样都要有。只有文件没有索引 = 找不回来的孤儿。"""
        result = self.service.attach(
            ORDER, PHASE_BORROW, [_FakeUpload("IMG_1.jpg", _photo_bytes())], "李四"
        )

        self.assertTrue(result.success, result.message)
        saved = result.data["saved"][0]
        self.assertEqual(saved["phase"], PHASE_BORROW)
        self.assertIsNotNone(self.store.load(saved["stored_name"]))
        rows = attachment_index_service.list_by_ref(REF_TYPE_ORDER, ORDER)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "evidence_borrow")

    def test_photo_is_compressed(self):
        """2400×1800 的原图进来，存下来的明显更小。"""
        source = _photo_bytes((3000, 2000))
        result = self.service.attach(
            ORDER, PHASE_BORROW, [_FakeUpload("IMG_1.jpg", source)], "李四"
        )

        saved = result.data["saved"][0]
        self.assertTrue(saved["compressed"])
        self.assertLess(saved["size_bytes"], len(source))

    def test_two_phases_do_not_overwrite_each_other(self):
        """同一张单既有发料照片又有回库照片，查的时候各归各的。"""
        self.service.attach(
            ORDER, PHASE_BORROW, [_FakeUpload("a.jpg", _photo_bytes())], "李四"
        )
        self.service.attach(
            ORDER, PHASE_RETURN, [_FakeUpload("b.jpg", _photo_bytes())], "李四"
        )

        self.assertEqual(self.service.count(ORDER, PHASE_BORROW), 1)
        self.assertEqual(self.service.count(ORDER, PHASE_RETURN), 1)
        self.assertEqual(self.service.count(ORDER), 2)

    def test_photos_are_scoped_to_their_order(self):
        """别的单的照片不会串进来。"""
        self.service.attach(
            ORDER, PHASE_BORROW, [_FakeUpload("a.jpg", _photo_bytes())], "李四"
        )

        self.assertEqual(self.service.count(ORDER_2), 0)

    def test_multiple_files_in_one_go(self):
        files = [_FakeUpload(f"{i}.jpg", _photo_bytes((800, 600))) for i in range(3)]
        result = self.service.attach(ORDER, PHASE_RETURN, files, "李四")

        self.assertEqual(len(result.data["saved"]), 3)
        self.assertEqual(self.service.count(ORDER, PHASE_RETURN), 3)

    def test_broken_image_is_kept_anyway(self):
        """处理不了的照片原样存下来——取证不能因为压缩失败就丢证据。"""
        result = self.service.attach(
            ORDER, PHASE_BORROW, [_FakeUpload("scan.jpg", b"broken-bytes")], "李四"
        )

        self.assertTrue(result.success, result.message)
        saved = result.data["saved"][0]
        self.assertFalse(saved["compressed"])
        self.assertEqual(self.store.load(saved["stored_name"]), b"broken-bytes")

    def test_missing_order_number_is_refused(self):
        result = self.service.attach(
            "", PHASE_BORROW, [_FakeUpload("a.jpg", _photo_bytes())], "李四"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "NO_ORDER")

    def test_empty_file_list_is_refused(self):
        result = self.service.attach(ORDER, PHASE_BORROW, [], "李四")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "NO_FILES")

    def test_unknown_phase_is_refused(self):
        result = self.service.attach(
            ORDER, "somewhere", [_FakeUpload("a.jpg", _photo_bytes())], "李四"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "BAD_PHASE")

    def test_oversize_after_compression_is_refused(self):
        """压完还超上限就拒绝——设置里写 8 MB 就该真按 8 MB 算。"""
        system_config_service.set(EvidenceConfig.MAX_MB, "1", "test")
        # 塞非图片内容绕过压缩，让体积原样超过 1 MB
        big = _FakeUpload("big.jpg", b"x" * (2 * 1024 * 1024))
        result = self.service.attach(ORDER, PHASE_BORROW, [big], "李四")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "NOTHING_SAVED")
        self.assertIn("超过单张上限", result.data["failed"][0])


class TestRequireSwitch(_Base):
    def test_empty_value_falls_back_to_default(self):
        """配置被清空不能等于「关掉」——那样取证要求会静默消失。"""
        system_config_service.set(EvidenceConfig.REQUIRE_BORROW, "", "test")
        self.assertTrue(self.service.require(PHASE_BORROW))

    def test_switch_off_lets_it_through(self):
        system_config_service.set(EvidenceConfig.REQUIRE_RETURN, "0", "test")

        check = self.service.check(ORDER, PHASE_RETURN)

        self.assertTrue(check.success)
        self.assertFalse(check.data["required"])

    def test_truthy_words_are_accepted(self):
        """超管手写成「是」「true」也得认。"""
        for word in ("true", "是", "ON"):
            system_config_service.set(EvidenceConfig.REQUIRE_BORROW, word, "test")
            self.assertTrue(self.service.require(PHASE_BORROW), word)

    def test_switch_on_blocks_without_a_photo(self):
        check = self.service.check(ORDER, PHASE_BORROW)

        self.assertFalse(check.success)
        self.assertEqual(check.error_code, "PHOTO_REQUIRED")

    def test_switch_on_passes_with_this_round_photo(self):
        check = self.service.check(ORDER, PHASE_BORROW, uploaded=2)
        self.assertTrue(check.success)

    def test_previous_photo_counts(self):
        """现场信号差，先拍后传是常态——同一笔交接有证据就不该被卡。"""
        self.service.attach(
            ORDER, PHASE_BORROW, [_FakeUpload("a.jpg", _photo_bytes())], "李四"
        )

        check = self.service.check(ORDER, PHASE_BORROW)

        self.assertTrue(check.success)
        self.assertTrue(check.data.get("existing"))

    def test_other_phase_photo_does_not_count(self):
        """归还照片不能顶借出照片用。"""
        self.service.attach(
            ORDER, PHASE_RETURN, [_FakeUpload("a.jpg", _photo_bytes())], "李四"
        )

        check = self.service.check(ORDER, PHASE_BORROW)

        self.assertFalse(check.success)


if __name__ == "__main__":
    unittest.main()
