"""编号生成器模块

提供统一的ID生成管理，使用单例模式集中管理所有编号生成逻辑，
包括试剂瓶编号、条码、领用记录编号、归还记录编号等。

并发安全 + 性能：
- 序号由 daily_counters 表在**事务内原子递增**产生（读取即 O(1)），
  避免旧实现"全表计数+1"在并发下产生重复编号；
- 同时保留基于 MAX() 前缀扫描的工具方法（_next_seq_from_max，
  以及各服务的 get_max_value_by_prefix），供数据修复/统计等场景备用。
"""
from datetime import datetime

from db.database import db
from utils.error_handler import logger

# 注意：services 层的实例通过方法内延迟导入获取，
# 避免工具层在模块级反向依赖服务层，导致循环导入。


class IDGenerator:
    """编号生成器（单例模式）

    统一管理系统中所有编号的生成逻辑，确保编号规则的一致性和可维护性。

    编号类型：
        - 试剂瓶编号：日期 + 4位序号（如 202606290001）
        - 试剂瓶条码：日期 + 4位序号（如 202605210001）
        - 领用记录编号：日期 + 4位序号（如 202606290001）
        - 归还记录编号：日期 + 4位序号（如 202606290001）

    并发安全：序号由 daily_counters 表在事务内原子递增产生，
    避免旧实现中"全表计数+1"在并发下产生重复编号的问题。
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

    @staticmethod
    def _next_seq_from_max(max_val: str, prefix: str) -> int:
        """从最大值中提取序号并 +1（备用的前缀扫描方案）

        Args:
            max_val: 当前最大值，如 "202606290005"
            prefix: 前缀，如 "20260629"

        Returns:
            下一个序号
        """
        try:
            current_seq = int(max_val[len(prefix):])
            return current_seq + 1
        except (ValueError, TypeError):
            return 1

    # ------------------------------------------------------------------
    # 序号原子递增（并发安全）
    # ------------------------------------------------------------------
    def _next_seq(self, key: str) -> int:
        """在事务内原子地获取下一个序号，保证同 key 下全局唯一递增。

        Args:
            key: 计数键，建议形如 "20260901"（瓶编号/条码）或
                 "bor:20260901" / "ret:20260901"（领用/归还，独立序列）

        Returns:
            下一个序号（从 1 开始）
        """
        with db.transaction():
            db.connection.execute(
                "INSERT OR IGNORE INTO daily_counters(counter_date, seq) VALUES(?, 0)",
                (key,),
            )
            db.connection.execute(
                "UPDATE daily_counters SET seq = seq + 1 WHERE counter_date = ?",
                (key,),
            )
            cur = db.connection.execute(
                "SELECT seq FROM daily_counters WHERE counter_date = ?", (key,)
            )
            row = cur.fetchone()
        return int(row[0]) if row else 1

    def _gen(self, key: str) -> str:
        """生成 "日期(8位) + 4位序号" 编号，序号由 daily_counters 原子分配。"""
        today = datetime.now().strftime("%Y%m%d")
        try:
            seq = self._next_seq(key)
            return f"{today}{seq:04d}"
        except Exception as e:
            logger.error(f"[IDGenerator] 生成编号失败(key={key}): {e}", exception=e)
            return f"{today}0001"

    # ------------------------------------------------------------------
    # 1. 试剂瓶编号生成（日期+四位自增）
    # ------------------------------------------------------------------
    def generate_bottle_number(self) -> str:
        """生成下一个试剂瓶编号（日期+四位自增）

        格式：YYYYMMDD + 4位自增数字（例：202606290001）
        同一日期内从 0001 开始自增，次日重置为 0001。

        Returns:
            试剂瓶编号字符串
        """
        return self._gen(datetime.now().strftime("%Y%m%d"))

    # ------------------------------------------------------------------
    # 2. 条码生成（日期+序号）
    # ------------------------------------------------------------------
    def generate_barcode(self) -> str:
        """生成唯一试剂瓶条码

        格式：YYYYMMDD + 4位自增数字（例：202605210001）

        Returns:
            生成的条码字符串
        """
        return self._gen(f"bar:{datetime.now().strftime('%Y%m%d')}")

    # ------------------------------------------------------------------
    # 3. 领用记录编号生成
    # ------------------------------------------------------------------
    def generate_borrow_record_number(self) -> str:
        """生成领用记录编号

        格式：YYYYMMDD + 4位自增数字（例：202606290001）

        Returns:
            领用记录编号字符串
        """
        return self._gen(f"bor:{datetime.now().strftime('%Y%m%d')}")

    # ------------------------------------------------------------------
    # 4. 归还记录编号生成
    # ------------------------------------------------------------------
    def generate_return_record_number(self) -> str:
        """生成归还记录编号

        格式：YYYYMMDD + 4位自增数字（例：202606290001）

        Returns:
            归还记录编号字符串
        """
        return self._gen(f"ret:{datetime.now().strftime('%Y%m%d')}")


# 全局单例实例
id_generator = IDGenerator()
