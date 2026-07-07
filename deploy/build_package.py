#!/usr/bin/env python3
"""打包发布脚本 - 创建可分发的安装包

用法：
    python deploy/build_package.py              # 创建 zip 安装包
    python deploy/build_package.py --exe         # 构建 PyInstaller exe
    python deploy/build_package.py --all         # 全部构建

输出：
    dist/ReagentManager-v0.88.zip              # 源码安装包
    dist/ReagentManager.exe                     # PyInstaller 可执行文件
"""
import os
import sys
import shutil
import zipfile
import subprocess
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "0.88"

# 打包时需要排除的文件和目录
EXCLUDE_PATTERNS = [
    '__pycache__', '.pyc', '.pyo', '.pyd',
    '.git', '.gitignore', '.gitattributes',
    '.pytest_cache', '.ruff_cache',
    'venv', '.venv', 'env',
    'build', 'dist', '*.egg-info',
    'logs', '*.log', '*.db',
    'test.py', 'test_db_connection.py',
    'agent_workflow',
    'VERIFICATION_REPORT.md',
    '=2.0.0',
]

# 需要包含的 docs 文件
INCLUDE_DOCS = [
    'docs/用户使用手册.md',
    'docs/部署说明.md',
]


def should_exclude(path):
    """判断文件是否应该排除"""
    name = os.path.basename(path)
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith('*'):
            if name.endswith(pattern[1:]):
                return True
        elif pattern in path or name == pattern:
            return True
    return False


def collect_files():
    """收集需要打包的文件列表"""
    files = []
    for root, dirs, filenames in os.walk(PROJECT_ROOT):
        # 过滤目录
        dirs[:] = [d for d in dirs if not should_exclude(d)]

        for fname in filenames:
            if should_exclude(fname):
                continue
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, PROJECT_ROOT)
            files.append((fpath, relpath))
    return files


def build_zip_package():
    """创建源码 zip 安装包"""
    print("=" * 60)
    print("  试剂库管理系统 - 打包工具")
    print("=" * 60)

    # 清理
    dist_dir = os.path.join(PROJECT_ROOT, 'dist')
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir, exist_ok=True)

    # 收集文件
    print("\n[1/3] 收集源文件...")
    files = collect_files()
    print(f"   已收集 {len(files)} 个文件")

    # 创建 zip 包
    zip_name = f"ReagentManager-v{VERSION}.zip"
    zip_path = os.path.join(dist_dir, zip_name)
    print(f"\n[2/3] 创建安装包: {zip_name}")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fpath, relpath in files:
            # 使用统一的前缀目录
            arcname = f"ReagentManager-v{VERSION}/{relpath}"
            zf.write(fpath, arcname)

        # 将 install.bat 和 install.sh 也放到根目录（方便用户双击运行）
        install_bat = os.path.join(PROJECT_ROOT, 'deploy', 'install.bat')
        install_sh = os.path.join(PROJECT_ROOT, 'deploy', 'install.sh')
        if os.path.isfile(install_bat):
            zf.write(install_bat, f"ReagentManager-v{VERSION}/install.bat")
        if os.path.isfile(install_sh):
            zf.write(install_sh, f"ReagentManager-v{VERSION}/install.sh")

    zip_size = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"   安装包大小: {zip_size:.1f} MB")

    # 创建 README
    print(f"\n[3/3] 生成安装说明...")
    readme_content = f"""试剂库管理系统 v{VERSION} - 安装说明
======================================

## 快速安装

### Windows 用户
1. 解压此 zip 文件到任意目录
2. 双击运行 install.bat（自动安装依赖 + 初始化数据库 + 创建管理员）
3. 安装完成后双击 run.bat 启动系统
4. 输入端口号（默认 8501），浏览器打开 http://localhost:端口号

### Linux/macOS 用户
1. 解压: unzip ReagentManager-v{VERSION}.zip
2. 进入目录: cd ReagentManager-v{VERSION}
3. 运行安装: bash install.sh
4. 启动服务: ./run.sh（输入端口号即可）
5. 浏览器打开 http://localhost:端口号

## 首次安装流程
install.bat / install.sh 会自动完成：
1. 创建 Python 虚拟环境
2. 安装所有依赖包
3. 初始化数据库（四库分离架构）
4. 提示输入超级管理员用户名和密码
5. 生成 run.bat / run.sh 启动脚本

## 日常使用
- Windows: 双击 run.bat → 输入端口号 → 自动启动
- Linux:   ./run.sh → 输入端口号 → 自动启动

## 系统要求
- Python 3.10+
- 4GB+ 可用内存
- 现代浏览器（Chrome/Firefox/Edge）

## 构建可执行文件
如需构建 .exe 文件（在目标平台上运行）:
    pip install pyinstaller
    python deploy/build_exe.py
"""
    readme_path = os.path.join(dist_dir, '安装说明.txt')
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)

    # 也把 readme 加入 zip
    with zipfile.ZipFile(zip_path, 'a', zipfile.ZIP_DEFLATED) as zf:
        zf.write(readme_path, f"ReagentManager-v{VERSION}/安装说明.txt")

    print(f"\n" + "=" * 60)
    print(f"  ✓ 打包完成！")
    print(f"  安装包: {zip_path}")
    print(f"  大小: {zip_size:.1f} MB")
    print(f"  包含: {len(files)} 个源文件")
    print("=" * 60)

    return zip_path


def build_exe_package():
    """构建 PyInstaller 可执行文件"""
    print("\n正在构建 PyInstaller 可执行文件...")
    build_script = os.path.join(PROJECT_ROOT, 'deploy', 'build_exe.py')
    subprocess.run([sys.executable, build_script, '--clean'], cwd=PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(description="试剂库管理系统打包工具")
    parser.add_argument('--exe', action='store_true', help='构建 PyInstaller 可执行文件')
    parser.add_argument('--all', action='store_true', help='构建所有格式安装包')
    parser.add_argument('--zip', action='store_true', help='仅构建 zip 安装包（默认）')
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    build_all = args.all
    build_zip = args.zip or (not args.exe and not args.all) or build_all
    build_exe = args.exe or build_all

    if build_zip:
        build_zip_package()

    if build_exe:
        build_exe_package()


if __name__ == '__main__':
    main()