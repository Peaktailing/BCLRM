"""ID 生成器单元测试（依赖数据库：验证 daily_counters 原子序号）

注意：本测试会调用 db.init_tables() 确保 daily_counters 表存在（幂等建表/加列，
不删除数据），并会推进真实库中的当日序号计数器。
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.id_generator import id_generator
from db.database import db


class TestIDGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 确保 daily_counters 等表存在（幂等，仅建表/加列，不删数据）
        db.init_tables()

    def test_bottle_number_format(self):
        n = id_generator.generate_bottle_number()
        # 8 位日期 + 4 位序号
        self.assertRegex(n, r"^\d{12}$")

    def test_bottle_number_increments_same_day(self):
        n1 = id_generator.generate_bottle_number()
        n2 = id_generator.generate_bottle_number()
        self.assertNotEqual(n1, n2)
        # 同日期内后生成的序号应更大
        self.assertGreater(int(n2[-4:]), int(n1[-4:]))

    def test_distinct_prefix_sequences(self):
        b = id_generator.generate_barcode()
        bo = id_generator.generate_borrow_record_number()
        r = id_generator.generate_return_record_number()
        # 三种编号均符合 "日期+4位序号" 格式
        for x in (b, bo, r):
            self.assertRegex(x, r"^\d{12}$")
        # 每种类型各自维护独立序列（均由 daily_counters 原子分配）
        b2 = id_generator.generate_barcode()
        self.assertGreater(int(b2[-4:]), int(b[-4:]))


if __name__ == "__main__":
    unittest.main()
