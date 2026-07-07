# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置文件

构建命令：
    pyinstaller deploy/ReagentManager.spec

输出：
    dist/ReagentManager/ReagentManager.exe  (Windows)
    dist/ReagentManager/ReagentManager      (Linux)
"""

import os
import sys

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 需要打包的源文件目录
SOURCE_DIRS = [
    'models', 'services', 'business', 'components',
    'db', 'utils', 'config', 'pages', 'scripts',
]

# 需要打包的单独文件
SOURCE_FILES = [
    'app.py', 'requirements.txt', 'README.md',
]

# 收集所有 .py 源文件
def collect_source_files():
    """收集项目中所有 Python 源文件"""
    datas = []
    for dir_name in SOURCE_DIRS:
        dir_path = os.path.join(PROJECT_ROOT, dir_name)
        if os.path.isdir(dir_path):
            for root, _, files in os.walk(dir_path):
                for f in files:
                    if f.endswith('.py') or f.endswith('.md'):
                        src = os.path.join(root, f)
                        # 计算相对路径用于目标目录
                        rel_dir = os.path.relpath(root, PROJECT_ROOT)
                        dest_dir = os.path.join('_internal', rel_dir)
                        datas.append((src, dest_dir))
    # 添加根目录文件
    for f in SOURCE_FILES:
        src = os.path.join(PROJECT_ROOT, f)
        if os.path.isfile(src):
            datas.append((src, '_internal'))
    return datas


a = Analysis(
    ['deploy/run.py'],  # 入口脚本
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=collect_source_files(),
    hiddenimports=[
        # Streamlit 相关隐藏导入
        'streamlit', 'streamlit.runtime', 'streamlit.web',
        'streamlit.commands', 'streamlit.elements',
        'streamlit.watcher', 'streamlit.proto',
        'streamlit.runtime.scriptrunner',
        # 项目模块
        'models', 'models.base', 'models.core', 'models.consumable',
        'services', 'services.base', 'services.core',
        'business', 'components', 'db', 'utils', 'config',
        'pages', 'scripts',
        # 依赖
        'pandas', 'matplotlib', 'openpyxl', 'pydantic',
        'requests', 'dotenv',
        'sqlite3',
        # 其他
        'watchdog', 'git', 'pyarrow',
        'altair', 'pillow', 'numpy',
        'packaging', 'protobuf', 'toml',
        'rich', 'click', 'blinker', 'cachetools',
        'tzdata', 'tzlocal', 'pydeck',
        'tenacity', 'tornado',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'test', 'tests',
        'pytest', 'setuptools', 'pip', 'wheel',
        'email', 'html', 'http', 'xml', 'xmlrpc',
        'pdb', 'doctest', 'argparse', 'distutils',
        'lib2to3', 'multiprocessing', 'concurrent',
        'asyncio', 'curses', 'idlelib',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# 收集所有 Streamlit 子模块
streamlit_imports = []
try:
    import streamlit
    import pkgutil
    streamlit_path = os.path.dirname(streamlit.__file__)
    for _, name, ispkg in pkgutil.iter_modules([streamlit_path]):
        streamlit_imports.append(f'streamlit.{name}')
        if ispkg:
            sub_path = os.path.join(streamlit_path, name)
            for _, sub_name, _ in pkgutil.iter_modules([sub_path]):
                streamlit_imports.append(f'streamlit.{name}.{sub_name}')
except ImportError:
    pass

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    a.zipfiles,
    [],
    name='ReagentManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 显示控制台窗口，方便查看启动日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)