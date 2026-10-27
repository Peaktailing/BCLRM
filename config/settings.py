"""全局配置：运行时路径一律从数据根派生，环境由 BCLRM_ENV 决定。

运行契约（见 docs/环境隔离与发布规划_执行版.md D08/D09/D14）：

- ``BCLRM_ENV``：``prod`` / ``beta`` / ``dev``，缺省 ``dev``。
- ``BCLRM_DATA_DIR``：prod/beta **必须显式设置**，且目录名必须与环境同名
  （``data/prod``、``data/beta``）。dev 允许缺省，回落仓库根。
- ``BCLRM_RELEASE_FILE``：prod/beta 必须指向本轨当前 release 的 ``release.json``。
  dev 允许缺省，此时版本取开发默认值，仅用于显示。
- ``BCLRM_MOBILE_UI``：``0``/``1``；dev 缺省开，prod/beta 缺省关。

四库、附件、日志全部从 ``DATA_DIR`` 派生，任何模块都不得再自行拼仓库路径。
prod/beta 配置不完整时在导入阶段直接抛错（fail-fast），不带着错配的数据根启动。
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

DATABASE_TYPE = "sqlite"  # 当前使用 SQLite 数据库

# 代码根目录：只用于定位代码与只读资源（如 docs/用户使用手册.md），
# 不作为任何运行时数据的落点。
BASE_DIR = Path(__file__).resolve().parent.parent

VALID_ENVS = ("prod", "beta", "dev")
#: dev 未配置 release 时的显示版本（四段纯数字，D03）
DEFAULT_DEV_VERSION = "0.8.16.0"


class ConfigError(RuntimeError):
    """运行时配置不合法：prod/beta 缺变量或变量互相矛盾。"""


def _read_env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _parse_env() -> str:
    raw = _read_env("BCLRM_ENV", "dev").lower()
    if raw not in VALID_ENVS:
        raise ConfigError(
            f"BCLRM_ENV 非法：{raw!r}，只允许 {', '.join(VALID_ENVS)}"
        )
    return raw


ENV: str = _parse_env()
IS_PROD: bool = ENV == "prod"
IS_BETA: bool = ENV == "beta"
IS_DEV: bool = ENV == "dev"


def _resolve_data_dir() -> Path:
    raw = _read_env("BCLRM_DATA_DIR")
    if not raw:
        if not IS_DEV:
            raise ConfigError(
                f"BCLRM_ENV={ENV} 时必须显式设置 BCLRM_DATA_DIR（绝对路径），"
                "否则多个 release 会共用同一份库"
            )
        return BASE_DIR

    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"BCLRM_DATA_DIR 必须是绝对路径：{raw!r}")
    path = path.resolve()

    if path == BASE_DIR:
        raise ConfigError(
            f"BCLRM_ENV={ENV} 的 BCLRM_DATA_DIR 不能等于代码目录 {BASE_DIR}"
        )
    if not IS_DEV and path.name != ENV:
        raise ConfigError(
            f"BCLRM_ENV={ENV} 的数据根目录名必须是 {ENV!r}，实际为 {path.name!r}：{path}"
        )
    return path


DATA_DIR: Path = _resolve_data_dir()
DB_DIR: Path = DATA_DIR / "db"

# ========== 四库分离架构 ==========
# 详见 docs/开发基础文档.md 数据库架构章节

# 1. 主业务库 (main.db) - 高频在线，核心必须在线
DB_MAIN_PATH = str(DB_DIR / "main.db")
DB_MAIN_NAME = "main.db"

# 2. 业务归档冷库 (archive_cold.db) - 过期数据，极低访问
DB_ARCHIVE_PATH = str(DB_DIR / "archive_cold.db")
DB_ARCHIVE_NAME = "archive_cold.db"

# 3. 附件索引库 (attach_cold.db) - 仅下载使用
DB_ATTACH_PATH = str(DB_DIR / "attach_cold.db")
DB_ATTACH_NAME = "attach_cold.db"

# 4. 审计日志库 (operation_log.db) - 纯追加写入
DB_LOG_PATH = str(DB_DIR / "operation_log.db")
DB_LOG_NAME = "operation_log.db"

# 日志目录
LOG_DIR = str(DATA_DIR / "logs")
ERROR_LOG_FILE = "error.log"

# 附件存储目录
ATTACHMENTS_DIR = str(DATA_DIR / "attachments")


def _parse_flag(raw: str, default: bool, name: str) -> bool:
    value = (raw or "").strip().lower()
    if not value:
        return default
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} 只接受 0/1（或 true/false），实际为 {raw!r}")


#: 手机取证入口开关。手机功能仍是预研，prod/beta 默认关闭（D11）。
MOBILE_UI: bool = _parse_flag(
    _read_env("BCLRM_MOBILE_UI"), default=IS_DEV, name="BCLRM_MOBILE_UI"
)


def _load_release() -> Dict[str, Any]:
    """读取本轨 release.json。prod/beta 缺失或格式错误直接拒绝启动。"""
    raw = _read_env("BCLRM_RELEASE_FILE")
    if not raw:
        if not IS_DEV:
            raise ConfigError(
                f"BCLRM_ENV={ENV} 时必须设置 BCLRM_RELEASE_FILE 指向本轨 release.json"
            )
        return {}

    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"BCLRM_RELEASE_FILE 必须是绝对路径：{raw!r}")
    if not path.is_file():
        raise ConfigError(f"release 文件不存在：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"release 文件无法解析：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"release 文件顶层必须是对象：{path}")
    return data


RELEASE_FILE: str = _read_env("BCLRM_RELEASE_FILE")
RELEASE: Dict[str, Any] = _load_release()
RELEASE_VERSION: str = str(RELEASE.get("version") or "").strip()
#: release.json 声明的四库 schema 版本；启动/部署/回滚逐项比对（D15）
SCHEMA_VERSIONS: Dict[str, int] = {
    str(k): int(v) for k, v in (RELEASE.get("schema_versions") or {}).items()
}


def _parse_version(value: str, source: str) -> str:
    """四段纯数字版本校验（D03）。"""
    parts = value.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        raise ConfigError(
            f"{source} 的版本必须是四段纯数字 MAJOR.MINOR.PATCH.BUILD：{value!r}"
        )
    return value


VERSION_NUMBER: str = (
    _parse_version(RELEASE_VERSION, "release.json")
    if RELEASE_VERSION
    else DEFAULT_DEV_VERSION
)

# 环境变量只做交叉校验，不作为版本事实源（D：release.json 为准）
_env_version = _read_env("BCLRM_VERSION")
if _env_version:
    _normalized = _env_version[1:] if _env_version.lower().startswith("v") else _env_version
    if RELEASE_VERSION and _normalized != RELEASE_VERSION:
        raise ConfigError(
            f"BCLRM_VERSION={_env_version!r} 与 release.json 版本 {RELEASE_VERSION!r} 不一致"
        )

#: 展示用版本（界面统一带 v 前缀）
VERSION = f"v{VERSION_NUMBER}"

# 审计日志保留天数（超过自动清理）
LOG_RETENTION_DAYS = 730  # 2年

# 主库数据行数上限（触发归档）
MAIN_DB_MAX_ROWS = 100000

# 过期数据归档年限
ARCHIVE_AFTER_YEARS = 3

# 会话安全
SESSION_TIMEOUT_MINUTES = 30  # 登录会话超时（分钟），超时需重新登录
DEFAULT_INITIAL_PASSWORD = "123456"  # 迁移期老账户首次登录密码，登录后请尽快在侧边栏修改

# 系统配置
SYSTEM_NAME = "试剂库管理系统"
DEFAULT_PAGE_SIZE = 100
DEFAULT_UNIT = "g"
EXPIRY_WARNING_DAYS = 30


def ensure_data_dirs() -> None:
    """创建数据根下的 db/logs/attachments（部署与启动时调用，幂等）。"""
    for path in (DB_DIR, Path(LOG_DIR), Path(ATTACHMENTS_DIR)):
        Path(path).mkdir(parents=True, exist_ok=True)


def describe_runtime(schema_map: Optional[Dict[str, int]] = None) -> str:
    """启动自检日志：环境、版本、release、数据根、手机开关、schema。"""
    schema = schema_map if schema_map is not None else SCHEMA_VERSIONS
    schema_text = ",".join(f"{k}={v}" for k, v in sorted(schema.items())) or "-"
    return (
        f"env={ENV} version={VERSION_NUMBER} release={RELEASE_FILE or '-'} "
        f"data_root={DATA_DIR} mobile_ui={int(MOBILE_UI)} schema=[{schema_text}]"
    )
