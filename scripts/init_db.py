"""初始化 SQLite 数据库（不依赖 pandas）

该脚本用于创建数据库表结构，无需 Excel 导入。
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.database import Database


def main():
    """初始化数据库"""
    print("=" * 60)
    print("数据库初始化工具")
    print("=" * 60)

    # 初始化数据库
    db = Database()
    print(f"\n数据库路径: {db.db_path}")

    # 创建所有表
    print("\n正在创建数据表...")
    db.init_tables()

    # 验证表是否创建成功
    print("\n验证表创建:")
    tables = [
        'person', 'storage_location', 'storage_requirement',
        'reagent_type', 'supplier', 'manufacturer',
        'controlled_list', 'chemical_info', 'reagent_bottle',
        'borrow_record', 'return_record', 'consumable'
    ]

    for table in tables:
        exists = db.table_exists(table)
        status = "✓" if exists else "✗"
        print(f"  {status} {table}")

    print("\n" + "=" * 60)
    print("数据库初始化完成！")
    print("=" * 60)
    print("\n提示: 数据库已创建，但暂无数据。")
    print("您可以通过以下方式添加数据:")
    print("  1. 安装 pandas: python3 -m pip install pandas openpyxl")
    print("  2. 运行导入脚本: python3 scripts/import_data.py")
    print("  3. 或直接在系统中通过界面添加数据")

    # 关闭数据库连接
    db.close()


if __name__ == "__main__":
    main()