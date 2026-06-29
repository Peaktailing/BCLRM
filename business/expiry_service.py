"""试剂过期判断业务服务

根据试剂类型、启封日期和当前日期判断试剂是否过期。

过期规则（启封后有效期）：
  - 普通固体试剂：5年（60个月）
  - 普通液体试剂：3年（36个月）
  - 胶体试剂/培养基：1年（12个月）
  - 标准品：2年（24个月）
  - 气体钢瓶：无有效期（标记为正常）
  - 生化试剂：1年（12个月）
  - 其他未识别类型：2年（24个月，保守估计）
"""
from datetime import datetime, timedelta
from typing import Optional

from models.core.reagent_bottle import ReagentBottle
from services.core.reagent_bottle_service import reagent_bottle_service
from utils.error_handler import logger, ServiceResult, handle_exception
from utils.field_mapper import ReagentBottleField


# 试剂类型 → 启封后有效期（月）
SHELF_LIFE_MONTHS = {
    "普通固体试剂": 60,
    "普通液体试剂": 36,
    "胶体试剂/培养基": 12,
    "标准品": 24,
    "气体钢瓶": None,       # 无有效期限制
    "生化试剂": 12,
}

# 默认有效期（未匹配到的类型）
DEFAULT_SHELF_LIFE_MONTHS = 24

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
        logger.info("ExpiryService 初始化完成")

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def check_bottle(self, bottle: ReagentBottle) -> str:
        """判断单个试剂瓶的过期状态（不写库）

        根据试剂类型和启封日期计算当前过期状态。

        Args:
            bottle: 试剂瓶对象

        Returns:
            过期状态字符串："正常" / "即将过期" / "已过期"
        """
        return self._compute_expired_flag(
            reagent_type=bottle.reagent_type,
            unseal_date=bottle.unseal_date,
        )

    def check_and_update(self, bottle: ReagentBottle) -> str:
        """判断并更新试剂瓶的过期状态（写库）

        计算当前过期状态，若与数据库中不一致则更新。

        Args:
            bottle: 试剂瓶对象

        Returns:
            过期状态字符串
        """
        new_flag = self.check_bottle(bottle)

        # 只在状态变化时写库
        if new_flag != bottle.expired_flag:
            try:
                self.bottle_service.update_by_field(
                    field_name=ReagentBottleField.BOTTLE_NUMBER,
                    field_value=bottle.bottle_number,
                    update_data={ReagentBottleField.EXPIRED_FLAG: new_flag},
                )
                logger.info(
                    "过期状态已更新",
                    bottle_number=bottle.bottle_number,
                    old=bottle.expired_flag,
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
                        field_value=bottle.bottle_number,
                        update_data={ReagentBottleField.EXPIRED_FLAG: new_flag},
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

    @staticmethod
    def _get_shelf_life(reagent_type: Optional[str]) -> Optional[int]:
        """获取试剂类型的启封后有效期（月）

        Args:
            reagent_type: 试剂类型名称

        Returns:
            有效期月数，None 表示永久有效
        """
        if not reagent_type:
            return DEFAULT_SHELF_LIFE_MONTHS

        return SHELF_LIFE_MONTHS.get(reagent_type, DEFAULT_SHELF_LIFE_MONTHS)

    @staticmethod
    def _compute_expired_flag(
        reagent_type: Optional[str],
        unseal_date: Optional[str],
    ) -> str:
        """计算过期状态

        Args:
            reagent_type: 试剂类型
            unseal_date: 启封日期（格式：YYYY/MM/DD HH:MM）

        Returns:
            "正常" / "即将过期" / "已过期"
        """
        # 未启封 → 正常
        if not unseal_date:
            return "正常"

        # 获取有效期
        shelf_months = ExpiryService._get_shelf_life(reagent_type)
        if shelf_months is None:
            # 永久有效（如气体钢瓶）
            return "正常"

        try:
            # 解析启封日期
            unseal_dt = datetime.strptime(unseal_date.strip()[:10], "%Y/%m/%d")
        except (ValueError, IndexError):
            # 解析失败，保守返回正常
            logger.warning("无法解析启封日期", unseal_date=unseal_date)
            return "正常"

        # 计算到期日期
        expiry_dt = unseal_dt + timedelta(days=shelf_months * 30)
        now = datetime.now()

        if now >= expiry_dt:
            return "已过期"

        if now >= expiry_dt - timedelta(days=EXPIRY_WARNING_DAYS):
            return "即将过期"

        return "正常"


# 全局单例
expiry_service = ExpiryService()