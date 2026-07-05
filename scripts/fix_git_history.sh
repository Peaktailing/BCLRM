#!/bin/bash
# 修改 Git 提交历史信息
# 这个脚本会修改提交 1026533 的提交信息

cd /home/biochm/Reagent-manager

echo "修改 Git 提交历史..."
echo ""
echo "原始提交信息: Initial commit: 试剂库管理系统 - 从 Teable 迁移到 SQLite"
echo "新提交信息:   feat: 试剂库管理系统初始化，从 Teable 迁移到 SQLite"
echo ""

# 使用 git rebase 来修改提交
# 首先，找到包含目标提交的分支
git rebase -i --root << EOF
pick 1026533 feat: 试剂库管理系统初始化，从 Teable 迁移到 SQLite
pick 7531909 docs: 添加 GitHub 认证配置指南和快速推送脚本
pick 9410da1 merge: 合并远程仓库的 .gitignore 配置
pick 85b55c8 refactor: 清理 Teable 相关代码，添加数据库测试页面
EOF

echo ""
echo "如果上面的命令打开了编辑器，请将第一行的 'pick' 改为 'reword'，"
echo "然后保存退出。"
