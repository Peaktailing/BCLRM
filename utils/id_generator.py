"""编号生成器模块

提供统一的ID生成管理，使用单例模式集中管理所有编号生成逻辑，
包括试剂瓶编号、条码、领用记录编号、归还记录编号等。
"""
from datetime import datetime
from utils.field_mapper import ReagentBottleField, BorrowRecordField, ReturnRecordField
from utils.error_handler import logger

# 注意：services 层的实例通过方法内延迟导入获取，
# 避免工具层在模块级反向依赖服务层，导致循环导入。


class IDGenerator:
    """编号生成器（单例模式）

    统一管理系统中所有编号的生成逻辑，确保编号规则的一致性和可维护性。

    支持的编号类型：
        - 试剂瓶编号：自增正整数
        - 试剂瓶条码：日期 + 4位序号（如 202605210001）
        - 领用记录编号：L + 时间戳（如 L20260521143025）
        - 归还记录编号：时间戳数字（如 20260521143025）
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

    # ------------------------------------------------------------------
    # 1. 试剂瓶编号生成（自增数字）
    # ------------------------------------------------------------------
    def generate_bottle_number(self) -> int:
        """生成下一个试剂瓶编号（自增正整数）

        查询当前所有试剂瓶的最大编号，返回最大值 + 1。

        Returns:
            下一个试剂瓶编号，失败返回 0

        Examples:
            >>> generator = IDGenerator()
            >>> generator.generate_bottle_number()
            42
        """
        try:
            from services.core.reagent_bottle_service import reagent_bottle_service
            bottles = reagent_bottle_service.get_all_parsed()
            if not bottles:
                return 1

            valid_numbers = [
                bottle.bottle_number
                for bottle in bottles
                if bottle.bottle_number and isinstance(bottle.bottle_number, (int, float))
            ]

            if not valid_numbers:
                return 1

            return max(valid_numbers) + 1
        except Exception as e:
            logger.error(f"[IDGenerator] 生成试剂瓶编号时发生错误: {e}", exception=e)
            return 0

    # ------------------------------------------------------------------
    # 2. 条码生成（日期+序号）
    # ------------------------------------------------------------------
    def generate_barcode(self) -> str:
        """生成唯一试剂瓶条码

        格式：YYYYMMDD + 4位自增数字（例：202605210001）

        Returns:
            生成的条码字符串，失败返回当天 0001 条码

        Examples:
            >>> generator = IDGenerator()
            >>> generator.generate_barcode()
            '202605210003'
        """
        today = datetime.now().strftime("%Y%m%d")
        try:
            from services.core.reagent_bottle_service import reagent_bottle_service
            bottles = reagent_bottle_service.get_all_parsed()
            today_count = sum(
                1 for bottle in bottles
                if bottle.barcode and str(bottle.barcode).startswith(today)
            )

            seq_num = today_count + 1
            return f"{today}{seq_num:04d}"
        except Exception as e:
            logger.error(f"[IDGenerator] 生成条码时发生错误: {e}", exception=e)
            return f"{today}0001"

    # ------------------------------------------------------------------
    # 3. 领用记录编号生成
    # ------------------------------------------------------------------
    def generate_borrow_record_number(self) -> str:
        """生成领用记录编号

        格式：L + YYYYMMDDHHMMSS（例：L20260521143025）

        Returns:
            领用记录编号字符串

        Examples:
            >>> generator = IDGenerator()
            >>> generator.generate_borrow_record_number()
            'L20260521143025'
        """
        try:
            from services.core.borrow_record_service import borrow_record_service
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            record_num = f"L{timestamp}"

            existing = borrow_record_service.get_all_parsed()
            count = sum(
                1 for rec in existing
                if rec.record_number and str(rec.record_number).startswith(record_num)
            )

            if count > 0:
                record_num = f"L{timestamp}{count + 1:02d}"

            return record_num
        except Exception as e:
            logger.error(f"[IDGenerator] 生成领用记录编号时发生错误: {e}", exception=e)
            return f"L{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # ------------------------------------------------------------------
    # 4. 归还记录编号生成
    # ------------------------------------------------------------------
    def generate_return_record_number(self) -> int:
        """生成归还记录编号

        格式：YYYYMMDDHHMMSS 时间戳数字（例：20260521143025）

        Returns:
            归还记录编号（整数），失败返回0

        Examples:
            >>> generator = IDGenerator()
            >>> generator.generate_return_record_number()
            20260521143025
        """
        try:
            from services.core.return_record_service import return_record_service
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            record_num = int(timestamp)

            existing = return_record_service.get_all_parsed()
            count = sum(
                1 for rec in existing
                if rec.return_number == record_num
            )

            if count > 0:
                record_num = int(f"{timestamp}{count + 1:02d}")

            return record_num
        except Exception as e:
            logger.error(f"[IDGenerator] 生成归还记录编号时发生错误: {e}", exception=e)
            return 0


# 全局单例实例
id_generator = IDGenerator()
