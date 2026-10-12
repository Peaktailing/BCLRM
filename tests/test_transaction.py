"""数据库事务嵌套与条件更新单元测试（QA 审查发现 M5/M6 的回归保护）"""
import unittest

from tests import TEST_DB
from db.database import db
from services.base.person_service import person_service


class TestNestedTransaction(unittest.TestCase):
    """嵌套事务：失败段只回滚自身，外层后续写入不受影响（SAVEPOINT 语义）。

    旧实现中嵌套段异常时跳过回滚，若外层继续执行并 COMMIT，失败段的
    半截写入会被落库（QA 审查发现 M5）。
    """

    _NAMES = ("外层写入", "内层写入", "嵌套成功")

    def tearDown(self):
        TEST_DB.connection.execute(
            "DELETE FROM person WHERE name IN (?, ?, ?)", self._NAMES
        )
        TEST_DB.connection.commit()

    def test_nested_failure_isolated(self):
        """内层失败：仅内层写入被回滚，外层写入保留。"""
        with db.transaction():
            person_service.create({"name": "外层写入", "role": "user"})
            try:
                with db.transaction():
                    person_service.create({"name": "内层写入", "role": "user"})
                    raise RuntimeError("模拟内层失败")
            except RuntimeError:
                pass

        names = {p["name"] for p in person_service.get_all()}
        self.assertIn("外层写入", names)
        self.assertNotIn("内层写入", names)

    def test_nested_success_merges(self):
        """嵌套成功：RELEASE 并入外层事务，随外层 COMMIT 落库。"""
        with db.transaction():
            with db.transaction():
                person_service.create({"name": "嵌套成功", "role": "user"})

        self.assertIsNotNone(person_service.get_by_name("嵌套成功"))


if __name__ == "__main__":
    unittest.main()
