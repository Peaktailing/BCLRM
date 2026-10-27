#!/usr/bin/env bash
# 发布前必须整体通过的质量门禁（执行版第 8 节）。
# 单项失败立即退出；不允许只看 pytest，也不允许沿用历史通过数。
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== 1/7 pytest =="
python3 -m pytest -q

echo "== 2/7 分层依赖 =="
python3 scripts/check_layers.py

echo "== 3/7 账目一致性 =="
python3 scripts/check_consistency.py

echo "== 4/7 页面体检（dev，手机开） =="
BCLRM_MOBILE_UI=1 python3 scripts/check_pages.py

echo "== 5/7 页面体检（prod 口径，手机关） =="
BCLRM_MOBILE_UI=0 python3 scripts/check_pages.py

echo "== 6/7 运行时只读检查 =="
python3 scripts/runtime_cli.py check

echo "== 7/7 配置闸门（缺数据根必须拒绝启动） =="
if BCLRM_ENV=prod BCLRM_DATA_DIR= python3 -c "import config.settings" 2>/dev/null; then
    echo "[FAIL] prod 缺少 BCLRM_DATA_DIR 却启动成功"
    exit 1
fi
if BCLRM_ENV=beta BCLRM_DATA_DIR= python3 -c "import config.settings" 2>/dev/null; then
    echo "[FAIL] beta 缺少 BCLRM_DATA_DIR 却启动成功"
    exit 1
fi
echo "[ OK ] prod/beta 缺数据根均拒绝启动"

echo "== 全部门禁通过 =="
