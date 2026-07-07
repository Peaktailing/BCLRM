"""试剂库管理系统 - 安装配置

使用方式：
    pip install -e .          # 开发模式安装
    python setup.py install   # 正式安装

安装后运行：
    reagent-manager           # 启动应用
    reagent-manager --init-db # 初始化数据库
    reagent-manager --add-users # 添加测试用户
"""
from setuptools import setup, find_packages

setup(
    name="reagent-manager",
    version="0.88",
    description="试剂库管理系统 - 化学实验室试剂全生命周期管理",
    author="Peaktailing",
    url="https://github.com/Peaktailing/BCLRM",
    packages=find_packages(
        include=["models", "models.*", "services", "services.*",
                 "business", "components", "db", "utils", "config", "scripts"]
    ),
    include_package_data=True,
    package_data={
        "": ["pages/*.py", "docs/*.md", "scripts/*.py"],
    },
    python_requires=">=3.10",
    install_requires=[
        "streamlit>=1.40.0",
        "requests>=2.31.0",
        "pandas>=2.0.0",
        "matplotlib>=3.10.0",
        "openpyxl>=3.1.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "reagent-manager=scripts.launcher:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)