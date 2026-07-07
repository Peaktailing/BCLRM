#!/bin/bash
# 试剂库管理系统 - Linux/macOS 安装脚本
# 用法: bash install.sh

set -e

echo "============================================================"
echo "  试剂库管理系统 v0.88 - 安装程序"
echo "  化学实验室试剂全生命周期管理"
echo "============================================================"
echo ""

# 检查 Python
echo "[1/4] 检查 Python 环境..."
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "[错误] 未检测到 Python，请先安装 Python 3.10+"
    echo "Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "CentOS/RHEL:   sudo yum install python3 python3-pip"
    echo "macOS:         brew install python3"
    exit 1
fi
echo "   已检测到 $($PYTHON --version)"

# 创建虚拟环境
echo ""
echo "[2/4] 创建虚拟环境..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo "   虚拟环境创建完成"
else
    echo "   虚拟环境已存在，跳过"
fi

# 激活虚拟环境并安装依赖
echo ""
echo "[3/4] 安装依赖包..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "   依赖安装完成"

# 创建启动脚本
echo ""
echo "[4/4] 创建快捷启动..."

cat > 启动试剂库管理系统.sh << 'SCRIPT'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
source venv/bin/activate
echo "正在启动试剂库管理系统..."
echo "服务启动后请在浏览器中打开 http://localhost:8501"
echo "按 Ctrl+C 停止服务"
echo ""
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
SCRIPT
chmod +x 启动试剂库管理系统.sh

cat > 初始化数据库.sh << 'SCRIPT'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
source venv/bin/activate
python scripts/launcher.py --init-db
echo "数据库初始化完成！"
SCRIPT
chmod +x 初始化数据库.sh

cat > 添加测试用户.sh << 'SCRIPT'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
source venv/bin/activate
python scripts/add_test_users.py
SCRIPT
chmod +x 添加测试用户.sh

echo ""
echo "============================================================"
echo "  安装完成！"
echo "============================================================"
echo ""
echo "使用方法:"
echo "  1. 运行 ./启动试剂库管理系统.sh 启动服务"
echo "  2. 浏览器打开 http://localhost:8501"
echo "  3. 首次使用请先运行 ./初始化数据库.sh"
echo "  4. 可选: 运行 ./添加测试用户.sh 创建测试账号"
echo ""
echo "默认测试账号:"
echo "  超级管理员: 潘汉 / admin123"
echo "  管理员:     潘汉2 / admin123"
echo "  教师:       潘汉3 / teacher123"
echo ""