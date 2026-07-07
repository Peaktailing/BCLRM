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

    zip_size = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"   安装包大小: {zip_size:.1f} MB")

    # 创建 README
    print(f"\n[3/3] 生成安装说明...")
    readme_content = f"""试剂库管理系统 v{VERSION} - 安装说明
======================================

## 快速安装

### Windows 用户
1. 解压此 zip 文件到任意目录
2. 双击运行 install.bat（自动安装依赖）
3. 双击 "启动试剂库管理系统.bat" 启动服务
4. 浏览器打开 http://localhost:8501

### Linux/macOS 用户
1. 解压: unzip ReagentManager-v{VERSION}.zip
2. 进入目录: cd ReagentManager-v{VERSION}
3. 运行安装: bash install.sh
4. 启动服务: ./启动试剂库管理系统.sh
5. 浏览器打开 http://localhost:8501

## 首次使用
1. 运行初始化数据库脚本
2. 可选: 运行添加测试用户脚本

## 默认测试账号
- 超级管理员: 潘汉 / admin123
- 管理员: 潘汉2 / admin123
- 教师: 潘汉3 / teacher123

## 系统要求
- Python 3.10+
- 4GB+ 可用内存
- 现代浏览器（Chrome/Firefox/Edge）

## 构建可执行文件
如需构建 .exe 文件:
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