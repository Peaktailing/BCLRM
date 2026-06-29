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
        - 试剂瓶编号：日期 + 4位序号（如 202606290001）
        - 试剂瓶条码：日期 + 4位序号（如 202605210001）
        - 领用记录编号：日期 + 4位序号（如 202606290001）
        - 归还记录编号：日期 + 4位序号（如 202606290001）
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
    # 1. 试剂瓶编号生成（日期+四位自增）
    # ------------------------------------------------------------------
    def generate_bottle_number(self) -> str:
        """生成下一个试剂瓶编号（日期+四位自增）

        格式：YYYYMMDD + 4位自增数字（例：202606290001）
        同一日期内从 0001 开始自增，次日重置为 0001。

        Returns:
            试剂瓶编号字符串，失败返回当天 0001

        Examples:
            >>> generator = IDGenerator()
            >>> generator.generate_bottle_number()
            '202606290003'
        """
        today = datetime.now().strftime("%Y%m%d")
        try:
            from services.core.reagent_bottle_service import reagent_bottle_service
            bottles = reagent_bottle_service.get_all_parsed()
            today_count = sum(
                1 for bottle in bottles
                if bottle.bottle_number and str(bottle.bottle_number).startswith(today)
            )

            seq_num = today_count + 1
            return f"{today}{seq_num:04d}"
        except Exception as e:
            logger.error(f"[IDGenerator] 生成试剂瓶编号时发生错误: {e}", exception=e)
            return f"{today}0001"

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

        格式：YYYYMMDD + 4位自增数字（例：202606290001）
        同一日期内从 0001 开始自增，次日重置。

        Returns:
            领用记录编号字符串

        Examples:
            >>> generator = IDGenerator()
            >>> generator.generate_borrow_record_number()
            '202606290003'
        """
        today = datetime.now().strftime("%Y%m%d")
        try:
            from services.core.borrow_record_service import borrow_record_service
            existing = borrow_record_service.get_all_parsed()
            today_count = sum(
                1 for rec in existing
                if rec.record_number and str(rec.record_number).startswith(today)
            )

            seq_num = today_count + 1
            return f"{today}{seq_num:04d}"
        except Exception as e:
            logger.error(f"[IDGenerator] 生成领用记录编号时发生错误: {e}", exception=e)
            return f"{today}0001"

    # ------------------------------------------------------------------
    # 4. 归还记录编号生成
    # ------------------------------------------------------------------
    def generate_return_record_number(self) -> str:
        """生成归还记录编号

        格式：YYYYMMDD + 4位自增数字（例：202606290001）
        同一日期内从 0001 开始自增，次日重置。

        Returns:
            归还记录编号字符串，失败返回当天 0001

        Examples:
            >>> generator = IDGenerator()
            >>> generator.generate_return_record_number()
            '202606290002'
        """
        today = datetime.now().strftime("%Y%m%d")
        try:
            from services.core.return_record_service import return_record_service
            existing = return_record_service.get_all_parsed()
            today_count = sum(
                1 for rec in existing
                if rec.return_number and str(rec.return_number).startswith(today)
            )

            seq_num = today_count + 1
            return f"{today}{seq_num:04d}"
        except Exception as e:
            logger.error(f"[IDGenerator] 生成归还记录编号时发生错误: {e}", exception=e)
            return f"{today}0001"


# 全局单例实例
id_generator = IDGenerator()
