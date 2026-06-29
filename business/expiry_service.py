"""试剂过期判断业务服务

根据试剂类型、生产日期、启封日期和当前日期判断试剂是否过期。

过期规则（两段日期判断）：
  - 未启封：使用生产日期 + 未启封有效时长（天）来判断是否过期
  - 已启封：使用启封日期 + 启封有效时长（天）来判断是否过期
  - 具体每个试剂的判断时长从化学品信息表（chemical_info）中获取：
      * unsealed_shelf_life（未启封有效时长，天）
      * sealed_shelf_life（启封有效时长，天）
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

from models.core.reagent_bottle import ReagentBottle
from services.core.reagent_bottle_service import reagent_bottle_service
from services.base.chemical_service import chemical_service
from utils.error_handler import logger, ServiceResult, handle_exception
from utils.field_mapper import ReagentBottleField


# 默认有效期（当化学品信息表中未设置时使用）
DEFAULT_UNSEALED_SHELF_LIFE_DAYS = 730    # 2年
DEFAULT_SEALED_SHELF_LIFE_DAYS = 365      # 1年

# 即将过期提醒阈值（天）
EXPIRY_WARNING_DAYS = 30


class ExpiryService:
    """试剂过期判断服务类

    封装所有过期判断相关的业务逻辑，包括：
    - 单个试剂的过期状态计算
    - 批量试剂过期状态更新
    - 过期数据统计
    """

    def __init__(self):
        self.bottle_service = reagent_bottle_service
        self.chemical_service = chemical_service
        logger.info("ExpiryService 初始化完成")

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def check_bottle(self, bottle: ReagentBottle, chemical_cache: Optional[Dict[str, Any]] = None) -> str:
        """判断单个试剂瓶的过期状态（不写库）

        根据试剂的生产日期/启封日期以及化学品信息表中的有效时长
        计算当前过期状态。

        Args:
            bottle: 试剂瓶对象
            chemical_cache: 可选的化学品信息缓存（用于批量查询优化）

        Returns:
            过期状态字符串："正常" / "即将过期" / "已过期"
        """
        # 查询化学品信息获取有效时长
        shelf_life_days = self._get_shelf_life_for_bottle(bottle, chemical_cache)

        # 根据是否启封选择判断逻辑
        if bottle.unseal_date:
            # 已启封：基于启封日期 + 启封有效时长
            return self._compute_by_date(bottle.unseal_date, shelf_life_days.sealed)
        else:
            # 未启封：基于生产日期 + 未启封有效时长
            return self._compute_by_date(bottle.production_date, shelf_life_days.unsealed)

    def check_and_update(self, bottle: ReagentBottle, chemical_cache: Optional[Dict[str, Any]] = None) -> str:
        """判断并更新试剂瓶的过期状态（写库）

        计算当前过期状态，若与数据库中不一致则更新。

        Args:
            bottle: 试剂瓶对象
            chemical_cache: 可选的化学品信息缓存（用于批量查询优化）

        Returns:
            过期状态字符串
        """
        new_flag = self.check_bottle(bottle, chemical_cache)

        # 只在状态变化时写库
        if new_flag != bottle.expired_flag:
            old_flag = bottle.expired_flag
            try:
                self.bottle_service.update_by_field(
                    field_name=ReagentBottleField.BOTTLE_NUMBER,
                    value=bottle.bottle_number,
                    fields={ReagentBottleField.EXPIRED_FLAG: new_flag},
                )
                # 同步内存对象
                bottle.expired_flag = new_flag
                logger.info(
                    "过期状态已更新",
                    bottle_number=bottle.bottle_number,
                    old=old_flag,
                    new=new_flag,
                )
            except Exception as e:
                logger.error(
                    "过期状态更新失败",
                    bottle_number=bottle.bottle_number,
                    exception=e,
                )

        return new_flag

    def sync_all(self) -> int:
        """同步所有试剂瓶的过期状态

        遍历所有试剂瓶，重新计算并更新过期状态。

        Returns:
            更新的试剂瓶数量
        """
        bottles = self.bottle_service.get_all_parsed()
        update_count = 0

        for bottle in bottles:
            new_flag = self.check_bottle(bottle)
            if new_flag != bottle.expired_flag:
                try:
                    self.bottle_service.update_by_field(
                        field_name=ReagentBottleField.BOTTLE_NUMBER,
                        value=bottle.bottle_number,
                        fields={ReagentBottleField.EXPIRED_FLAG: new_flag},
                    )
                    update_count += 1
                except Exception as e:
                    logger.error(
                        "过期状态同步失败",
                        bottle_number=bottle.bottle_number,
                        exception=e,
                    )

        logger.info("过期状态同步完成", total=len(bottles), updated=update_count)
        return update_count

    def get_expired_bottles(self) -> list:
        """获取所有已过期的试剂瓶

        Returns:
            过期试剂瓶对象列表
        """
        bottles = self.bottle_service.get_all_parsed()
        return [b for b in bottles if self.check_bottle(b) == "已过期"]

    def get_expiring_bottles(self) -> list:
        """获取所有即将过期的试剂瓶

        Returns:
            即将过期试剂瓶对象列表
        """
        bottles = self.bottle_service.get_all_parsed()
        return [b for b in bottles if self.check_bottle(b) == "即将过期"]

    @handle_exception(context="过期统计")
    def get_expiry_stats(self) -> ServiceResult[dict]:
        """获取过期统计数据

        Returns:
            ServiceResult[dict] - 包含正常/即将过期/已过期数量
        """
        bottles = self.bottle_service.get_all_parsed()
        normal = expiring = expired = 0

        for bottle in bottles:
            flag = self.check_bottle(bottle)
            if flag == "已过期":
                expired += 1
            elif flag == "即将过期":
                expiring += 1
            else:
                normal += 1

        return ServiceResult.ok(data={
            "normal": normal,
            "expiring": expiring,
            "expired": expired,
            "total": len(bottles),
        })

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_shelf_life_for_bottle(self, bottle: ReagentBottle, chemical_cache: dict = None) -> '_ShelfLife':
        """获取试剂瓶对应的有效时长

        优先从化学品信息表（chemical_info）中按试剂名称或CAS号查找，
        若未找到或未设置，则使用系统默认值。

        Args:
            bottle: 试剂瓶对象
            chemical_cache: 可选的化学品信息缓存字典（key: name 或 cas_number）

        Returns:
            _ShelfLife 命名元组（unsealed, sealed）
        """
        # 使用缓存避免重复查询
        chem_info = None
        if chemical_cache is not None:
            if bottle.reagent_name:
                chem_info = chemical_cache.get(f"name:{bottle.reagent_name}")
            if not chem_info and bottle.cas_number:
                chem_info = chemical_cache.get(f"cas:{bottle.cas_number}")
        else:
            # 无缓存时执行查询
            if bottle.reagent_name:
                chem_info = self.chemical_service.get_by_name(bottle.reagent_name)
            if not chem_info and bottle.cas_number:
                chem_info = self.chemical_service.get_by_cas_number(bottle.cas_number)

        if chem_info:
            unsealed = chem_info.unsealed_shelf_life
            sealed = chem_info.sealed_shelf_life
            return _ShelfLife(
                unsealed=unsealed if unsealed is not None else DEFAULT_UNSEALED_SHELF_LIFE_DAYS,
                sealed=sealed if sealed is not None else DEFAULT_SEALED_SHELF_LIFE_DAYS,
            )

        return _ShelfLife(
            unsealed=DEFAULT_UNSEALED_SHELF_LIFE_DAYS,
            sealed=DEFAULT_SEALED_SHELF_LIFE_DAYS,
        )

    @staticmethod
    def _compute_by_date(
        date_str: Optional[str],
        shelf_life_days: int,
    ) -> str:
        """基于日期和有效天数计算过期状态

        Args:
            date_str: 起始日期字符串（格式：YYYY/MM/DD ...）
            shelf_life_days: 有效天数

        Returns:
            "正常" / "即将过期" / "已过期"
        """
        # 没有起始日期 → 无法判断，返回正常
        if not date_str:
            return "正常"

        # shelf_life_days=0 表示立即过期
        if shelf_life_days == 0:
            return "已过期"

        # shelf_life_days 为 None 或负数时返回正常
        if shelf_life_days is None or shelf_life_days < 0:
            return "正常"

        try:
            # 支持多种日期格式：YYYY/MM/DD, YYYY-MM-DD, YYYY.MM.DD
            date_clean = date_str.strip()[:10].replace('-', '/').replace('.', '/')
            start_dt = datetime.strptime(date_clean, "%Y/%m/%d")
        except (ValueError, IndexError):
            logger.warning("无法解析日期", date_str=date_str)
            return "正常"

        # 计算到期日期
        expiry_dt = start_dt + timedelta(days=shelf_life_days)
        now = datetime.now()

        if now >= expiry_dt:
            return "已过期"

        if now >= expiry_dt - timedelta(days=EXPIRY_WARNING_DAYS):
            return "即将过期"

        return "正常"


class _ShelfLife:
    """有效时长值对象"""
    def __init__(self, unsealed: int, sealed: int):
        self.unsealed = unsealed
        self.sealed = sealed


# 全局单例
expiry_service = ExpiryService()