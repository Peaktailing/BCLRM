# 数据库配置
DATABASE_TYPE = "sqlite"  # 当前使用 SQLite 数据库

# ========== 四库分离架构 ==========
# 详见 docs/开发基础文档.md 数据库架构章节

# 1. 主业务库 (main.db) - 高频在线，核心必须在线
DB_MAIN_PATH = "db/main.db"
DB_MAIN_NAME = "main.db"

# 2. 业务归档冷库 (archive_cold.db) - 过期数据，极低访问
DB_ARCHIVE_PATH = "db/archive_cold.db"
DB_ARCHIVE_NAME = "archive_cold.db"

# 3. 附件索引库 (attach_cold.db) - 仅下载使用
DB_ATTACH_PATH = "db/attach_cold.db"
DB_ATTACH_NAME = "attach_cold.db"

# 4. 审计日志库 (operation_log.db) - 纯追加写入
DB_LOG_PATH = "db/operation_log.db"
DB_LOG_NAME = "operation_log.db"

# WAL 日志独立目录
WAL_DIR_MAIN = "db_wal/main"
WAL_DIR_ARCHIVE = "db_wal/archive"
WAL_DIR_ATTACH = "db_wal/attach"
WAL_DIR_LOG = "db_wal/logdb"

# 日志目录
LOG_DIR = "logs"
ERROR_LOG_FILE = "error.log"

# 附件存储目录
ATTACHMENTS_DIR = "attachments"

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
VERSION = "v0.86"