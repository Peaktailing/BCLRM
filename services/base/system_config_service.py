"""系统配置：键值对形式的运行时开关。

**为什么不是常量。** ``config/settings.py`` 放的是「改了就错」的东西——表名、
路径、四库分离的文件名。而「借出到底要不要拍照」这类问题的答案取决于这个
实验室的危化品管理口径，学期初可能收紧、期末可能放宽，改一次就发一次版
是不合理的。所以这类开关进库，由超管在「系统设置」页当场改。

**为什么不是一列一字段。** 每加一个开关就 ``ALTER TABLE`` 一次，加十次就有
十次迁移；而开关本身没有关联查询的需求——只有「按 key 取一个值」。键值表
在这种形态下是对的，代价是丢掉了列类型，所以值的读写一律走 ``get_bool`` /
``get_int`` 这类显式转换，不让调用方自己去猜 "1" 和 "true"。

**没有缓存。** 一次主键查找在本地 SQLite 上是微秒级，而缓存要处理失效，
页面每帧重跑时反而更容易读到旧值。省下的那点开销不值一个 bug。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from db.base_service import BaseService
from db.database import db
from utils.audit import audit
from utils.error_handler import logger
from utils.field_mapper import SystemConfigField

_CONFIG_TABLE = "system_config"

#: 真值口径。写成 "1"/"0" 是给数据库看的，读的时候两种都认。
_TRUE_VALUES = {"1", "true", "yes", "on", "是", "开"}


class SystemConfigService(BaseService):
    """系统配置读写。"""

    def __init__(self, database=None) -> None:
        super().__init__(_CONFIG_TABLE, database or db)

    # ---------------------------------------------------------------- 读
    def get(self, key: str, default: str = "") -> str:
        """读一项配置。表还没建时返回默认值。

        为什么吞掉异常：老库要重启应用才会由 ``init_tables()`` 建这张表，
        而页面不会等。让「表不存在」直接抛到界面上，等于一次升级就把所有
        依赖配置的页面变成白屏——为一个可选开关付这个代价不值得。
        """
        try:
            row = self.get_by_field(SystemConfigField.CONFIG_KEY, key)
        except Exception as exc:
            logger.warning(f"读取系统配置失败（system_config 表可能还没建）：{exc}")
            return default
        if not row:
            return default
        value = row.get(SystemConfigField.CONFIG_VALUE)
        return default if value is None else str(value)

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.get(key, "1" if default else "0")
        return str(raw).strip().lower() in _TRUE_VALUES

    def get_int(self, key: str, default: int = 0) -> int:
        raw = self.get(key, str(default))
        try:
            return int(float(str(raw).strip()))
        except (TypeError, ValueError):
            return default

    def as_dict(self) -> Dict[str, str]:
        """全部配置（页面展示用）。表没建时返回空。"""
        try:
            rows = self.get_all(order_by=SystemConfigField.CONFIG_KEY)
        except Exception as exc:
            logger.warning(f"读取系统配置列表失败：{exc}")
            return {}
        return {
            row[SystemConfigField.CONFIG_KEY]: row.get(SystemConfigField.CONFIG_VALUE) or ""
            for row in rows
        }

    # ---------------------------------------------------------------- 写
    def set(
        self,
        key: str,
        value: Any,
        operator: str = "",
        remark: Optional[str] = None,
    ) -> bool:
        """写入或更新一项配置。值统一转成文本——键值表没有列类型。"""
        key = (key or "").strip()
        if not key:
            logger.warning("系统配置写入失败：键为空")
            return False
        text = "" if value is None else str(value)
        try:
            row = self.get_by_field(SystemConfigField.CONFIG_KEY, key)
        except Exception as exc:
            logger.error(f"系统配置写入失败（表不存在？）：{exc}")
            return False
        payload = {
            SystemConfigField.CONFIG_VALUE: text,
            SystemConfigField.UPDATED_BY: operator,
        }
        if remark is not None:
            payload[SystemConfigField.REMARK] = remark
        if row:
            ok = self.update(row[SystemConfigField.ID], payload)
        else:
            payload[SystemConfigField.CONFIG_KEY] = key
            ok = bool(self.create(payload))
        if ok:
            audit(operator, "更新系统配置", _CONFIG_TABLE, key, text)
        return ok

    def set_many(self, values: Dict[str, Any], operator: str = "") -> int:
        return sum(1 for key, value in values.items() if self.set(key, value, operator))


# ---------------------------------------------------------------- 已知键
#
# 键名带前缀分组，便于在页面上分区展示，也便于将来做「这是哪个模块的开关」。
class EvidenceConfig:
    """现场取证相关键。"""

    #: 借出（批准执行领用）时必须上传发料现场照片
    REQUIRE_BORROW = "evidence.require_borrow"
    #: 归还时必须上传回库照片（剩余量、瓶身状态）
    REQUIRE_RETURN = "evidence.require_return"
    #: 单张照片大小上限（MB）
    MAX_MB = "evidence.max_mb"
    #: 照片保留天数（0 = 永久）
    KEEP_DAYS = "evidence.keep_days"
    #: 手机访问基地址（生成瓶身二维码用，如 http://192.168.1.10:8601）
    MOBILE_BASE_URL = "mobile.base_url"


#: 出厂默认值。缺省时按这些取值，等于「不用配置也能用」。
DEFAULTS = {
    EvidenceConfig.REQUIRE_BORROW: "1",
    EvidenceConfig.REQUIRE_RETURN: "1",
    EvidenceConfig.MAX_MB: "8",
    EvidenceConfig.KEEP_DAYS: "180",
    EvidenceConfig.MOBILE_BASE_URL: "",
}


def default_of(key: str) -> str:
    return DEFAULTS.get(key, "")


def ensure_defaults(operator: str = "system") -> int:
    """补齐缺失的默认项（幂等，启动时调用一次）。

    只在「这条键不存在」时写入：已经有了就说明人改过（哪怕是改成空串），
    启动时不该把人为的关掉又打开。
    """
    written = 0
    for key, value in DEFAULTS.items():
        if system_config_service.get_by_field(SystemConfigField.CONFIG_KEY, key):
            continue
        if system_config_service.create(
            {
                SystemConfigField.CONFIG_KEY: key,
                SystemConfigField.CONFIG_VALUE: value,
                SystemConfigField.UPDATED_BY: operator,
                SystemConfigField.REMARK: "出厂默认",
            }
        ):
            written += 1
    return written


system_config_service = SystemConfigService()

__all__ = [
    "SystemConfigService",
    "system_config_service",
    "EvidenceConfig",
    "DEFAULTS",
    "default_of",
    "ensure_defaults",
]
