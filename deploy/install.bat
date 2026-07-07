@echo off
chcp 65001 >nul
title 试剂库管理系统 - 安装程序

echo ============================================================
echo   试剂库管理系统 v0.88 - 安装程序
echo   化学实验室试剂全生命周期管理
echo ============================================================
echo.

:: 检查 Python
echo [1/4] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   已检测到 Python %%v

:: 创建虚拟环境
echo.
echo [2/4] 创建虚拟环境...
if not exist "venv" (
    python -m venv venv
    echo   虚拟环境创建完成
) else (
    echo   虚拟环境已存在，跳过
)

:: 激活虚拟环境并安装依赖
echo.
echo [3/4] 安装依赖包...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
echo   依赖安装完成

:: 复制启动脚本
echo.
echo [4/4] 创建快捷启动...
echo @echo off > 启动试剂库管理系统.bat
echo call venv\Scripts\activate.bat >> 启动试剂库管理系统.bat
echo echo 正在启动试剂库管理系统... >> 启动试剂库管理系统.bat
echo echo 服务启动后请在浏览器中打开 http://localhost:8501 >> 启动试剂库管理系统.bat
echo echo 按 Ctrl+C 停止服务 >> 启动试剂库管理系统.bat
echo echo. >> 启动试剂库管理系统.bat
echo streamlit run app.py --server.port 8501 --server.address 0.0.0.0 >> 启动试剂库管理系统.bat

echo @echo off > 初始化数据库.bat
echo call venv\Scripts\activate.bat >> 初始化数据库.bat
echo python scripts\launcher.py --init-db >> 初始化数据库.bat
echo echo 数据库初始化完成！ >> 初始化数据库.bat
echo pause >> 初始化数据库.bat

echo @echo off > 添加测试用户.bat
echo call venv\Scripts\activate.bat >> 添加测试用户.bat
echo python scripts\add_test_users.py >> 添加测试用户.bat
echo pause >> 添加测试用户.bat

echo.
echo ============================================================
echo   安装完成！
echo ============================================================
echo.
echo 使用方法:
echo   1. 双击 "启动试剂库管理系统.bat" 启动服务
echo   2. 浏览器打开 http://localhost:8501
echo   3. 首次使用请先运行 "初始化数据库.bat"
echo   4. 可选: 运行 "添加测试用户.bat" 创建测试账号
echo.
echo 默认测试账号:
echo   超级管理员: 潘汉 / admin123
echo   管理员:     潘汉2 / admin123
echo   教师:       潘汉3 / teacher123
echo.
pause