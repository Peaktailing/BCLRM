#!/bin/bash
# 快速推送脚本 - 需要 GitHub Personal Access Token

echo "======================================"
echo "GitHub 推送脚本"
echo "======================================"
echo ""

# 检查是否提供了 token
if [ -z "$1" ]; then
    echo "使用方法: bash scripts/quick_push.sh <YOUR_GITHUB_TOKEN>"
    echo ""
    echo "获取 Token 方法："
    echo "1. 登录 GitHub"
    echo "2. Settings → Developer settings → Personal access tokens"
    echo "3. Generate new token (classic)"
    echo "4. 勾选 repo 权限"
    echo "5. 生成后复制 token"
    echo ""
    echo "示例："
    echo "  bash scripts/quick_push.sh ghp_xxxxxxxxxxxx"
    exit 1
fi

TOKEN="$1"
REPO_URL="https://github.com/Peaktailing/BCLRM.git"

echo "正在配置远程仓库..."
cd /home/biochm/Reagent-manager

# 修改远程 URL 包含 token
git remote set-url origin "https://${TOKEN}@github.com/Peaktailing/BCLRM.git"

echo "✓ 远程仓库已配置"
echo ""

# 推送代码
echo "正在推送代码到 GitHub..."
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "======================================"
    echo "✓ 推送成功！"
    echo "======================================"
    echo ""
    echo "代码已推送到："
    echo "  $REPO_URL"
    echo ""
    echo "后续操作："
    echo "  1. 访问仓库确认代码"
    echo "  2. 如果需要，可以修改远程 URL 移除 token："
    echo "     git remote set-url origin $REPO_URL"
else
    echo ""
    echo "======================================"
    echo "✗ 推送失败！"
    echo "======================================"
    echo ""
    echo "可能的原因："
    echo "  1. Token 无效或已过期"
    echo "  2. 没有仓库访问权限"
    echo "  3. Token 缺少 repo 权限"
    echo ""
    echo "请参考文档：docs/GITHUB_AUTH.md"
fi
