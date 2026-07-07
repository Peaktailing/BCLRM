#!/usr/bin/env python3
"""试剂库管理系统 - 命令行启动器

安装后可使用 `reagent-manager` 命令启动系统。

用法：
    reagent-manager              # 启动 Web 应用
    reagent-manager --init-db    # 初始化数据库
    reagent-manager --add-users  # 添加测试用户
    reagent-manager --version    # 显示版本
"""
import sys
import os
import subprocess


def main():
    # 确保工作目录正确
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    args = sys.argv[1:]

    if "--version" in args or "-v" in args:
        from config.settings import VERSION
        print(f"试剂库管理系统 {VERSION}")
        return

    if "--init-db" in args:
        print("正在初始化数据库...")
        from db.database import Database
        db = Database()
        db.init_tables()
        from db.multi_database import db_manager
        db_manager.init_all_databases()
        print("数据库初始化完成！")
        return

    if "--add-users" in args:
        print("正在添加测试用户...")
        subprocess.run([sys.executable, "scripts/add_test_users.py"], cwd=project_root)
        return

    # 默认：启动 Streamlit 应用
    print("正在启动试剂库管理系统...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", "8501", "--server.address", "0.0.0.0"],
        cwd=project_root
    )


if __name__ == "__main__":
    main()