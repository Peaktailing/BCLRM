#!/usr/bin/env python3
"""试剂库管理系统 - 命令行启动器

用法：
    reagent-manager              # 启动 Web 应用
    reagent-manager --port 8501  # 指定端口启动
    reagent-manager --init-db    # 初始化数据库
    reagent-manager --setup      # 首次安装：初始化数据库 + 创建管理员
    reagent-manager --version    # 显示版本
"""
import sys
import os
import subprocess
import getpass


def init_database():
    """初始化数据库（建表 + 迁移，幂等）"""
    from db.database import Database
    db = Database()
    db.init_tables()
    print("✓ 数据库初始化完成")


def setup_first_admin():
    """交互式创建第一个超级管理员"""
    from services.base.person_service import PersonService
    ps = PersonService()

    print("\n" + "=" * 50)
    print("  创建超级管理员账号")
    print("=" * 50)

    while True:
        name = input("\n请输入管理员用户名: ").strip()
        if name:
            break
        print("用户名不能为空！")

    while True:
        password = getpass.getpass("请输入密码（至少6位）: ")
        if len(password) < 6:
            print("密码至少需要6位！")
            continue
        password2 = getpass.getpass("请再次输入密码确认: ")
        if password != password2:
            print("两次密码不一致，请重新输入！")
            continue
        break

    ps.create({"name": name, "role": "super_admin"})
    result = ps.set_password(name, password)
    if result.is_success():
        print(f"\n✓ 超级管理员 '{name}' 创建成功！")
    else:
        print(f"\n✗ 创建失败: {result.message}")
        sys.exit(1)


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)

    args = sys.argv[1:]

    if "--version" in args or "-v" in args:
        from config.settings import VERSION
        print(f"试剂库管理系统 {VERSION}")
        return

    if "--init-db" in args:
        print("正在初始化数据库...")
        init_database()
        return

    if "--setup" in args:
        print("试剂库管理系统 - 首次安装\n")
        init_database()
        setup_first_admin()
        print("\n安装完成！运行以下命令启动：")
        print("  reagent-manager")
        return

    # 提取端口号
    port = "8501"
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            port = args[i + 1]
            break

    # 启动 Streamlit
    print(f"正在启动试剂库管理系统（端口 {port}）...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", port, "--server.address", "0.0.0.0"],
        cwd=project_root
    )


if __name__ == "__main__":
    main()