#!/bin/bash
# 修改 Git 提交历史信息脚本
# 将不规范的提交信息改为标准格式

set -e

echo "======================================"
echo "修改 Git 提交历史信息"
echo "======================================"

# 检查是否在 git 仓库中
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "错误: 当前目录不是 Git 仓库"
    exit 1
fi

# 显示当前提交历史
echo ""
echo "当前提交历史:"
git log --oneline

echo ""
echo "======================================"
echo "即将修改的提交:"
echo "  1026533: 'Initial commit: 试剂库管理系统 - 从 Teable 迁移到 SQLite'"
echo "  将改为:   'feat: 试剂库管理系统初始化，从 Teable 迁移到 SQLite'"
echo ""
read -p "是否继续? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "取消操作"
    exit 0
fi

# 使用 git filter-branch 修改提交信息
echo "正在修改提交历史..."

# 创建临时脚本用于修改提交信息
cat > /tmp/fix-commit-msg.sh << 'SCRIPT'
#!/bin/bash

if [ "$GIT_COMMIT" = "1026533" ]; then
    echo "feat: 试剂库管理系统初始化，从 Teable 迁移到 SQLite"
else
    cat "$1"
fi
SCRIPT

chmod +x /tmp/fix-commit-msg.sh

# 使用 filter-branch 修改提交信息
git filter-branch -f --msg-filter 'if echo "$GIT_COMMIT" | grep -q "1026533"; then
    echo "feat: 试剂库管理系统初始化，从 Teable 迁移到 SQLite"
else
    cat
fi' HEAD~3..HEAD

# 清理备份
rm -rf .git/refs/original/

echo ""
echo "======================================"
echo "✓ 修改完成！"
echo "======================================"
echo ""
echo "新的提交历史:"
git log --oneline

echo ""
echo "需要强制推送才能更新远程仓库:"
echo "  git push --force origin main"
echo ""
echo "⚠️ 警告: 强制推送会覆盖远程历史，请确保没有其他协作者在同时工作"
