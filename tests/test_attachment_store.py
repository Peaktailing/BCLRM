"""附件存储（utils/attachment_store.py）单元测试

使用临时目录，不污染 attachments/；附件索引写入真实 attach_cold.db（幂等小数据）。
"""
import tempfile
import unittest
from pathlib import Path

from utils.attachment_store import AttachmentStore


class _FakeUpload:
    """模拟 Streamlit UploadedFile（只需 name 与 getvalue()）"""

    def __init__(self, name: str, content: bytes = b"PDF-BYTES"):
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


class TestAttachmentStore(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = AttachmentStore(base_dir=self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_and_load_roundtrip(self):
        """保存后可按存储名读回，索引可查原始文件名"""
        stored = self.store.save(_FakeUpload("乙醇MSDS.pdf"), allowed_exts=["pdf"], ref_type="chemical")
        self.assertIsNotNone(stored)
        self.assertNotEqual(stored, "乙醇MSDS.pdf")  # 加了随机前缀
        content = self.store.load(stored)
        self.assertEqual(content, b"PDF-BYTES")
        self.assertEqual(self.store.original_name(stored), "乙醇MSDS.pdf")

    def test_save_none_returns_none(self):
        """无文件返回 None"""
        self.assertIsNone(self.store.save(None))

    def test_reject_disallowed_extension(self):
        """扩展名不在白名单内拒绝"""
        with self.assertRaises(ValueError):
            self.store.save(_FakeUpload("evil.exe"), allowed_exts=["pdf"])

    def test_reject_oversize(self):
        """超过大小上限拒绝"""
        big = _FakeUpload("big.pdf", content=b"0" * (2 * 1024 * 1024))
        with self.assertRaises(ValueError):
            self.store.save(big, allowed_exts=["pdf"], max_mb=1)

    def test_path_traversal_blocked(self):
        """路径穿越：保存时剥离路径组件，读取/删除时拦截"""
        stored = self.store.save(_FakeUpload("../evil.pdf"), allowed_exts=["pdf"])
        # basename 剥离后不含 ..
        self.assertNotIn("..", stored)
        # 直接构造穿越名读取/删除应被拦截
        self.assertIsNone(self.store.load("../../etc/passwd"))
        self.assertFalse(self.store.delete("../../etc/passwd"))

    def test_delete_removes_file_and_index(self):
        """删除后文件与索引均不存在"""
        stored = self.store.save(_FakeUpload("a.pdf"), allowed_exts=["pdf"])
        self.assertTrue(Path(self.store.base_dir, stored).is_file())
        self.assertTrue(self.store.delete(stored))
        self.assertIsNone(self.store.load(stored))
        self.assertIsNone(self.store.original_name(stored))

    def test_load_missing_file_returns_none(self):
        """历史数据（文件缺失）返回 None 而非报错"""
        self.assertIsNone(self.store.load("deadbeef_missing.pdf"))


if __name__ == "__main__":
    unittest.main()
