# 数据库配置
# 当前使用 SQLite 数据库（替代原有的 Teable）
DATABASE_TYPE = "sqlite"  # 可选值：sqlite, teable

# SQLite 数据库配置
DB_NAME = "reagent.db"
DB_PATH = "db/reagent.db"  # 数据库文件路径

# Teable 连接配置（已废弃，保留用于兼容）
# 本地Docker部署地址
TEABLE_BASE_URL = "http://localhost:3000"
TEABLE_API_TOKEN = "teable_acc18jWxz0U4AiW7njx_X3NKEQ52Q3hU4DLoZXHkMsFPmw5xKFElUG7L8jsQMlM="

# 表ID映射（已废弃，保留用于兼容）
TABLE_IDS = {
    ## 核心业务表
    "reagent_bottle": "tblc71S7dbkg0VuBPhO",
    ##借出记录表
    "borrow_record": "tbltQ6rcCFngZUABHrO",
    ##还入记录表
    "return_record": "tblJhsv7PMN64TDrI1P",
    ##化学品信息表
    "chemical_info": "tblekF6RbxeM8hxKg5Z",
    ##管控化学品表
    "controlled_list": "tblADJrUzMY7y8e0JyO",
    ##化学品类型表
    "reagent_type": "tbluMJDrAG6X2upDwch",
    ##存储要求表
    "storage_requirement": "tblE5PeFF7U8OkepP4f",
    ##人员信息表
    "person": "tblYeUq1W3cz5L63Ktb",
    ##试剂供应商
    "supplier": "tblDsotPoQTyEqc4mqV",
    ##试剂制造商
    "manufacturer": "tbltXMxojZRiF6BnPcZ",
    ##存储位置
    "storage_location": "tblgU3kwk9AacP1E0L3"
}

# 系统配置
SYSTEM_NAME = "试剂库管理系统"
DEFAULT_PAGE_SIZE = 100
DEFAULT_UNIT = "g"
EXPIRY_WARNING_DAYS = 30
VERSION = "v0.2.0"  # 更新版本号，标记数据库迁移