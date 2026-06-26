#!/bin/bash
# Git 仓库绑定脚本
# 用于将项目绑定到远程 Git 仓库

set -e

echo "======================================"
echo "Git 仓库绑定脚本"
echo "======================================"

# 检查 git 是否安装
if ! command -v git &> /dev/null; then
    echo "错误: Git 未安装"
    echo "请先安装 Git:"
    echo "  Ubuntu/Debian: sudo apt-get install git"
    echo "  CentOS/RHEL:   sudo yum install git"
    echo "  macOS:         brew install git"
    exit 1
fi

# 项目根目录
PROJECT_DIR="/home/biochm/Reagent-manager"

# 远程仓库地址
REMOTE_URL="https://github.com/Peaktailing/BCLRM.git"

# 切换到项目目录
cd "$PROJECT_DIR"

echo ""
echo "项目目录: $PROJECT_DIR"
echo "远程仓库: $REMOTE_URL"
echo ""

# 检查是否是 git 仓库
if [ -d ".git" ]; then
    echo "✓ Git 仓库已存在"

    # 检查远程仓库配置
    if git remote get-url origin &> /dev/null; then
        echo "⚠ 当前远程仓库配置:"
        echo "  origin: $(git remote get-url origin)"
        echo ""
        read -p "是否要更新远程仓库地址? (y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git remote set-url origin "$REMOTE_URL"
            echo "✓ 远程仓库地址已更新"
        else
            echo "保持原有配置不变"
        fi
    else
        echo "添加远程仓库..."
        git remote add origin "$REMOTE_URL"
        echo "✓ 远程仓库已添加"
    fi
else
    echo "初始化 Git 仓库..."
    git init

    echo "添加所有文件到暂存区..."
    git add .

    echo "创建初始提交..."
    git commit -m "Initial commit - 试剂库管理系统迁移到 SQLite"

    echo "添加远程仓库..."
    git remote add origin "$REMOTE_URL"

    echo "✓ Git 仓库初始化完成"
fi

echo ""
echo "======================================"
echo "Git 配置信息"
echo "======================================"
echo ""
echo "远程仓库:"
git remote -v
echo ""
echo "当前分支:"
git branch
echo ""

# 询问是否推送到远程
read -p "是否推送到远程仓库? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "推送到远程仓库..."
    # 注意：首次推送可能需要身份验证
    # 如果仓库是空的，可以使用 -u origin master
    # 如果有其他分支或 master 不存在，可能需要调整
    git push -u origin $(git symbolic-ref --short HEAD 2>/dev/null || echo "master")
    echo "✓ 推送完成"
else
    echo "跳过推送"
fi

echo ""
echo "======================================"
echo "✓ Git 仓库绑定完成！"
echo "======================================"
echo ""
echo "后续操作建议:"
echo "1. 确保远程仓库配置正确"
echo "2. 在 GitHub/GitLab 上检查仓库设置"
echo "3. 如需推送，可能需要配置 SSH 密钥或访问令牌"
echo ""
