# Git 仓库绑定说明

## 项目已准备好绑定到远程仓库

远程仓库地址：`https://github.com/Peaktailing/BCLRM.git`

## 自动绑定脚本

已创建自动化脚本：[scripts/setup_git.sh](scripts/setup_git.sh)

### 使用方法

1. **确保已安装 Git**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update && sudo apt-get install git

   # CentOS/RHEL
   sudo yum install git

   # macOS
   brew install git
   ```

2. **运行脚本**
   ```bash
   cd /home/biochm/Reagent-manager
   bash scripts/setup_git.sh
   ```

### 脚本功能

✅ 检查 Git 是否已安装  
✅ 检测是否为 Git 仓库  
✅ 配置远程仓库地址  
✅ 添加 .gitignore 配置  
✅ 创建初始提交（可选）  
✅ 推送到远程仓库（可选）  

## 手动绑定（可选）

如果不使用脚本，可以手动执行以下命令：

### 1. 检查 Git 状态
```bash
git status
```

### 2. 查看远程仓库配置
```bash
git remote -v
```

### 3. 添加远程仓库
```bash
# 如果还没有远程仓库
git remote add origin https://github.com/Peaktailing/BCLRM.git

# 如果已有远程仓库，需要更新
git remote set-url origin https://github.com/Peaktailing/BCLRM.git
```

### 4. 验证配置
```bash
git remote -v
```

## 注意事项

⚠️ **数据库文件**：已将 `db/*.db` 添加到 .gitignore，不会被提交  
⚠️ **首次推送**：可能需要 GitHub 认证或配置 SSH 密钥  
⚠️ **初始提交**：建议创建一个初始提交记录项目状态  

## 分支命名建议

项目使用以下分支策略：
- `main` 或 `master` - 主分支
- `dev` - 开发分支
- `feature/*` - 功能分支

## 后续步骤

1. ✅ 仓库已创建并配置
2. ⏳ 执行脚本或手动命令
3. ⏳ 推送到远程：`git push -u origin master`
4. ⏳ 在 GitHub 上检查仓库

## 故障排除

### 问题：Permission denied
**解决方案**：配置 GitHub 访问令牌或 SSH 密钥

### 问题：Repository not found
**解决方案**：确保远程仓库地址正确，且你有访问权限

### 问题：![rejected]
**解决方案**：先拉取远程更改 `git pull origin master --allow-unrelated-histories`
