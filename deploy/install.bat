@echo off
chcp 65001 >nul
title 试剂库管理系统 - 安装程序

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ============================================================
echo   试剂库管理系统 v0.88 - 首次安装
echo   化学实验室试剂全生命周期管理
echo ============================================================
echo.
echo 本程序将完成以下操作：
echo   1. 创建 Python 虚拟环境
echo   2. 安装依赖包
echo   3. 初始化数据库
echo   4. 创建超级管理员账号
echo.

:: ── 检查 Python ──────────────────────────────────────────
echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo       已检测到 Python %%v

:: ── 创建虚拟环境 ──────────────────────────────────────────
echo.
echo [2/5] 创建虚拟环境...
if not exist "venv" (
    python -m venv venv
    echo       虚拟环境创建完成
) else (
    echo       虚拟环境已存在，跳过
)

:: ── 安装依赖 ──────────────────────────────────────────────
echo.
echo [3/5] 安装依赖包（可能需要几分钟）...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
echo       依赖安装完成

:: ── 初始化数据库 ──────────────────────────────────────────
echo.
echo [4/5] 初始化数据库...
python -c "from db.database import Database; d=Database(); d.init_tables(); from db.multi_database import db_manager; db_manager.init_all_databases(); print('数据库初始化完成')"

:: ── 创建超级管理员 ────────────────────────────────────────
echo.
echo [5/5] 创建超级管理员账号
echo.
echo ════════════════════════════════════════════════════════
echo   请设置超级管理员账号（首次登录使用）
echo ════════════════════════════════════════════════════════
echo.

:INPUT_USERNAME
set "ADMIN_USER="
set /p ADMIN_USER="请输入管理员用户名: "
if "%ADMIN_USER%"=="" (
    echo 用户名不能为空，请重新输入。
    goto INPUT_USERNAME
)

:INPUT_PASSWORD
set "ADMIN_PASS="
set /p ADMIN_PASS="请输入密码（至少6位）: "
if "%ADMIN_PASS%"=="" (
    echo 密码不能为空，请重新输入。
    goto INPUT_PASSWORD
)

set "ADMIN_PASS2="
set /p ADMIN_PASS2="请再次输入密码确认: "
if not "%ADMIN_PASS%"=="%ADMIN_PASS2%" (
    echo 两次密码不一致，请重新设置。
    goto INPUT_PASSWORD
)

:: 创建管理员
python -c "import sys; sys.path.insert(0,'.'); from services.base.person_service import PersonService; ps=PersonService(); ps.create({'name':r'%ADMIN_USER%','role':'super_admin'}); r=ps.set_password(r'%ADMIN_USER%',r'%ADMIN_PASS%'); print('超级管理员创建成功！' if r.is_success() else f'创建失败: {r.message}')"

:: ── 生成启动脚本 ──────────────────────────────────────────
echo.
echo 正在生成启动脚本...

(
echo @echo off
echo chcp 65001 ^>nul
echo set "SCRIPT_DIR=%%~dp0"
echo cd /d "%%SCRIPT_DIR%%"
echo.
echo echo ============================================================
echo echo   试剂库管理系统 v0.88
echo echo ============================================================
echo echo.
echo set /p PORT="请输入端口号（默认 8501）: "
echo if "%%PORT%%"=="" set PORT=8501
echo.
echo echo 正在启动服务，请稍候...
echo echo 浏览器打开 http://localhost:%%PORT%%
echo echo 按 Ctrl+C 停止服务
echo echo.
echo call venv\Scripts\activate.bat
echo streamlit run app.py --server.port %%PORT%% --server.address 0.0.0.0 --server.headless true
echo pause
) > "%SCRIPT_DIR%run.bat"

echo @echo off > "%SCRIPT_DIR%初始化数据库.bat"
echo cd /d "%%~dp0" >> "%SCRIPT_DIR%初始化数据库.bat"
echo call venv\Scripts\activate.bat >> "%SCRIPT_DIR%初始化数据库.bat"
echo python -c "from db.database import Database; d=Database(); d.init_tables(); from db.multi_database import db_manager; db_manager.init_all_databases(); print('数据库初始化完成')" >> "%SCRIPT_DIR%初始化数据库.bat"
echo pause >> "%SCRIPT_DIR%初始化数据库.bat"

echo.
echo ============================================================
echo   安装完成！
echo ============================================================
echo.
echo 使用方法：
echo   - 双击 run.bat 启动系统（输入端口号即可）
echo   - 浏览器打开 http://localhost:端口号
echo.
echo 超级管理员账号：
echo   用户名: %ADMIN_USER%
echo   密码:   %ADMIN_PASS%（请妥善保管）
echo.
echo 如需重新初始化，请运行 "初始化数据库.bat"
echo.
pause