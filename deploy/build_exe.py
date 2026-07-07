#!/usr/bin/env python3
"""PyInstaller 构建脚本

在目标平台上运行此脚本以构建可执行文件。

用法：
    python deploy/build_exe.py          # 构建单文件 exe
    python deploy/build_exe.py --clean  # 清理后重新构建
    python deploy/build_exe.py --dir    # 构建目录模式（调试用）

输出：
    dist/ReagentManager.exe  (Windows)
    dist/ReagentManager      (Linux/macOS)

前置条件：
    1. 安装 Python 3.10+
    2. pip install -r requirements.txt
    3. pip install pyinstaller
"""
import os
import sys
import shutil
import subprocess
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_dependencies():
    """检查构建依赖"""
    print("=" * 60)
    print("  试剂库管理系统 - 构建工具")
    print("=" * 60)

    # 检查 PyInstaller
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("✗ PyInstaller 未安装，正在安装...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
        print("✓ PyInstaller 安装完成")

    # 检查项目依赖
    req_file = os.path.join(PROJECT_ROOT, 'requirements.txt')
    print(f"✓ 依赖文件: {req_file}")


def clean_build():
    """清理之前的构建产物"""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for d in dirs_to_clean:
        path = os.path.join(PROJECT_ROOT, d)
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"✓ 清理: {d}")
    # 清理 .spec 生成的缓存
    for f in os.listdir(PROJECT_ROOT):
        if f.endswith('.spec'):
            path = os.path.join(PROJECT_ROOT, f)
            if 'ReagentManager' not in f:
                os.remove(path)


def build_exe(onedir=False):
    """构建可执行文件"""
    spec_file = os.path.join(PROJECT_ROOT, 'deploy', 'ReagentManager.spec')

    print(f"\n正在构建可执行文件...")
    print(f"Spec 文件: {spec_file}")

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        '--distpath', os.path.join(PROJECT_ROOT, 'dist'),
        '--workpath', os.path.join(PROJECT_ROOT, 'build'),
    ]

    if onedir:
        cmd.append('--onedir')
    else:
        cmd.append('--onefile')

    cmd.append(spec_file)

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("  ✓ 构建成功！")
        print("=" * 60)

        dist_dir = os.path.join(PROJECT_ROOT, 'dist')
        if os.path.exists(dist_dir):
            print(f"\n输出文件位于: {dist_dir}")
            for f in os.listdir(dist_dir):
                fpath = os.path.join(dist_dir, f)
                size_mb = os.path.getsize(fpath) / (1024 * 1024)
                if os.path.isfile(fpath):
                    print(f"  {f} ({size_mb:.1f} MB)")

        print(f"\n使用方法:")
        if sys.platform == 'win32':
            print(f"  双击 dist\\ReagentManager.exe")
        else:
            print(f"  ./dist/ReagentManager")
    else:
        print("\n✗ 构建失败，请检查错误信息")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="试剂库管理系统构建工具")
    parser.add_argument('--clean', action='store_true', help='清理后重新构建')
    parser.add_argument('--dir', action='store_true', help='构建目录模式（调试用）')
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    check_dependencies()

    if args.clean:
        clean_build()

    build_exe(onedir=args.dir)


if __name__ == '__main__':
    main()