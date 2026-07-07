#!/bin/bash
# 试剂库管理系统 - Linux/macOS 首次安装脚本
# 用法: bash install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  试剂库管理系统 v0.88 - 首次安装"
echo "  化学实验室试剂全生命周期管理"
echo "============================================================"
echo ""
echo "本程序将完成以下操作："
echo "  1. 创建 Python 虚拟环境"
echo "  2. 安装依赖包"
echo "  3. 初始化数据库"
echo "  4. 创建超级管理员账号"
echo ""

# ── 检查 Python ──────────────────────────────────────────
echo "[1/5] 检查 Python 环境..."
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo ""
    echo "[错误] 未检测到 Python，请先安装 Python 3.10+"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  CentOS/RHEL:   sudo yum install python3 python3-pip"
    echo "  macOS:         brew install python3"
    exit 1
fi
echo "      已检测到 $($PYTHON --version)"

# ── 创建虚拟环境 ──────────────────────────────────────────
echo ""
echo "[2/5] 创建虚拟环境..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo "      虚拟环境创建完成"
else
    echo "      虚拟环境已存在，跳过"
fi

# ── 安装依赖 ──────────────────────────────────────────────
echo ""
echo "[3/5] 安装依赖包（可能需要几分钟）..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "      依赖安装完成"

# ── 初始化数据库 ──────────────────────────────────────────
echo ""
echo "[4/5] 初始化数据库..."
python -c "
from db.database import Database
d = Database()
d.init_tables()
from db.multi_database import db_manager
db_manager.init_all_databases()
print('数据库初始化完成')
"

# ── 创建超级管理员 ────────────────────────────────────────
echo ""
echo "[5/5] 创建超级管理员账号"
echo ""
echo "════════════════════════════════════════════════════════"
echo "  请设置超级管理员账号（首次登录使用）"
echo "════════════════════════════════════════════════════════"
echo ""

while true; do
    read -r -p "请输入管理员用户名: " ADMIN_USER
    if [ -n "$ADMIN_USER" ]; then
        break
    fi
    echo "用户名不能为空，请重新输入。"
done

while true; do
    read -r -s -p "请输入密码（至少6位）: " ADMIN_PASS
    echo ""
    if [ -z "$ADMIN_PASS" ]; then
        echo "密码不能为空，请重新输入。"
        continue
    fi
    read -r -s -p "请再次输入密码确认: " ADMIN_PASS2
    echo ""
    if [ "$ADMIN_PASS" != "$ADMIN_PASS2" ]; then
        echo "两次密码不一致，请重新设置。"
        continue
    fi
    break
done

# 创建管理员
python -c "
import sys
sys.path.insert(0, '.')
from services.base.person_service import PersonService
ps = PersonService()
ps.create({'name': '$ADMIN_USER', 'role': 'super_admin'})
r = ps.set_password('$ADMIN_USER', '$ADMIN_PASS')
print('超级管理员创建成功！' if r.is_success() else f'创建失败: {r.message}')
"

# ── 生成启动脚本 ──────────────────────────────────────────
echo ""
echo "正在生成启动脚本..."

cat > "$SCRIPT_DIR/run.sh" << 'RUNSCRIPT'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  试剂库管理系统 v0.88"
echo "============================================================"
echo ""

read -r -p "请输入端口号（默认 8501）: " PORT
PORT=${PORT:-8501}

echo ""
echo "正在启动服务，请稍候..."
echo "浏览器打开 http://localhost:$PORT"
echo "按 Ctrl+C 停止服务"
echo ""

source venv/bin/activate
streamlit run app.py --server.port "$PORT" --server.address 0.0.0.0 --server.headless true
RUNSCRIPT
chmod +x "$SCRIPT_DIR/run.sh"

cat > "$SCRIPT_DIR/初始化数据库.sh" << 'DBSCRIPT'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
source venv/bin/activate
python -c "
from db.database import Database
d = Database()
d.init_tables()
from db.multi_database import db_manager
db_manager.init_all_databases()
print('数据库初始化完成')
"
DBSCRIPT
chmod +x "$SCRIPT_DIR/初始化数据库.sh"

echo ""
echo "============================================================"
echo "  安装完成！"
echo "============================================================"
echo ""
echo "使用方法："
echo "  - 运行 ./run.sh 启动系统（输入端口号即可）"
echo "  - 浏览器打开 http://localhost:端口号"
echo ""
echo "超级管理员账号："
echo "  用户名: $ADMIN_USER"
echo "  密码:   $ADMIN_PASS（请妥善保管）"
echo ""
echo "如需重新初始化，请运行 ./初始化数据库.sh"
echo ""