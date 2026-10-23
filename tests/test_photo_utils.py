"""照片预处理单元测试（utils/photo_utils.py）。

只测会真实咬人的四件事：

1. EXIF 方向的转正 —— 不转正，手机竖拍的照片在系统里全是躺着的。
2. 长边缩放 —— 不缩，一个学期附件目录涨到几十 G。
3. 小图不放大 —— 放大了只会更糊、更大。
4. 压不了也不丢 —— 取证不能因为压缩失败就把证据扔了。
"""
import io
import unittest

from PIL import Image

from utils.photo_utils import (
    ALLOWED_EXTS,
    PhotoError,
    guess_ext,
    human_size,
    is_supported,
    normalize,
    normalize_or_original,
)


def _jpeg(size=(3000, 2000), color=(200, 30, 30)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


class TestNormalize(unittest.TestCase):
    def test_long_edge_is_capped(self):
        """4000×3000 进来，长边压到 1600。"""
        source = _jpeg((4000, 3000))
        data, size = normalize(source, max_edge=1600)
        self.assertEqual(size[0], 1600)
        self.assertEqual(size[1], 1200)
        self.assertLess(len(data), len(source))

    def test_small_image_is_not_enlarged(self):
        """比上限小的图不放大——放大只会更糊、更大。"""
        source = _jpeg((400, 300))
        data, size = normalize(source, max_edge=1600)
        self.assertEqual(size, (400, 300))

    def test_output_is_jpeg(self):
        data, _ = normalize(_jpeg((800, 600)))
        self.assertEqual(data[:2], b"\xff\xd8")   # JPEG 的 SOI 标记

    def test_png_with_alpha_goes_white_not_black(self):
        """透明 PNG 铺白底。直接用 convert('RGB') 会让透明处变黑。"""
        image = Image.new("RGBA", (100, 100), (255, 0, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data, _ = normalize(buffer.getvalue(), max_edge=1600)
        with Image.open(io.BytesIO(data)) as out:
            self.assertEqual(out.getpixel((50, 50)), (255, 255, 255))

    def test_exif_orientation_is_applied(self):
        """带 Orientation=6（顺时针 90°）的图，转正后宽高互换。"""
        image = Image.new("RGB", (400, 200), (10, 200, 10))
        exif = image.getexif()
        exif[274] = 6                     # 274 = Orientation
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", exif=exif)
        data, size = normalize(buffer.getvalue(), max_edge=1600)
        self.assertEqual(size, (200, 400))

    def test_garbage_is_rejected(self):
        with self.assertRaises(PhotoError):
            normalize(b"not an image at all")

    def test_empty_is_rejected(self):
        with self.assertRaises(PhotoError):
            normalize(b"")

    def test_compression_failure_keeps_original(self):
        """压不了就原样返回并标记没压成——证据不能因为压缩失败就丢。"""
        raw = b"not an image at all"
        data, compressed = normalize_or_original(raw)
        self.assertEqual(data, raw)
        self.assertFalse(compressed)


class TestHelpers(unittest.TestCase):
    def test_guess_ext(self):
        self.assertEqual(guess_ext("IMG_0012.HEIC"), "heic")
        self.assertEqual(guess_ext("无扩展名"), "jpg")

    def test_heic_is_not_in_the_whitelist(self):
        """HEIC 故意不在白名单：Pillow 默认不认，存进去就是打不开的文件。"""
        self.assertNotIn("heic", ALLOWED_EXTS)
        self.assertFalse(is_supported("photo.heic"))
        self.assertTrue(is_supported("photo.JPG"))

    def test_human_size(self):
        self.assertEqual(human_size(0), "0 KB")
        self.assertIn("KB", human_size(2048))
        self.assertIn("MB", human_size(3 * 1024 * 1024))


if __name__ == "__main__":
    unittest.main()
