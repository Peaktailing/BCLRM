# GitHub 认证配置指南

## 问题说明

执行 `git push` 时需要 GitHub 身份验证。有以下几种解决方案：

## 方案一：使用 GitHub Personal Access Token（推荐）

### 1. 创建 Personal Access Token
1. 登录 GitHub
2. 进入 Settings → Developer settings → Personal access tokens
3. 点击 "Generate new token (classic)"
4. 设置：
   - Note: "Reagent Manager"
   - Expiration: 选择合适的时间
   - Select scopes: 勾选 `repo` (Full control of private repositories)
5. 点击 "Generate token"
6. **重要**：保存好生成的 token（只会显示一次）

### 2. 配置 Git 使用 Token

#### 方法 A：修改远程 URL（简单）
```bash
# 将远程 URL 改为包含 token 的格式
git remote set-url origin https://<YOUR_TOKEN>@github.com/Peaktailing/BCLRM.git

# 然后再次推送
git push -u origin main
```

#### 方法 B：使用 Git Credential Store
```bash
# 首次推送时输入用户名和 token
git push -u origin main

# 用户名：你的 GitHub 用户名
# 密码：使用 Personal Access Token
```

### 3. 测试推送
```bash
git push -u origin main
```

## 方案二：使用 SSH 密钥（推荐用于长期使用）

### 1. 检查是否已有 SSH 密钥
```bash
ls -la ~/.ssh/
```

### 2. 生成新的 SSH 密钥（如果没有）
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```
按 Enter 接受默认位置，可以设置密码也可以不设置。

### 3. 添加 SSH 密钥到 SSH Agent
```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### 4. 在 GitHub 添加 SSH 密钥
1. 复制公钥内容：
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
2. 登录 GitHub
3. 进入 Settings → SSH and GPG keys
4. 点击 "New SSH key"
5. 粘贴公钥内容，添加标题
6. 点击 "Add SSH key"

### 5. 修改远程仓库为 SSH 格式
```bash
git remote set-url origin git@github.com:Peaktailing/BCLRM.git
```

### 6. 测试连接
```bash
ssh -T git@github.com
```

看到 "Hi username! You've successfully authenticated" 就成功了。

### 7. 推送代码
```bash
git push -u origin main
```

## 方案三：使用 GitHub CLI

如果安装了 GitHub CLI：
```bash
# 登录
gh auth login

# 设置远程仓库
gh repo set-default Peaktailing/BCLRM

# 推送
git push -u origin main
```

## 快速开始（复制粘贴）

### 如果你选择方案一（Token）
执行以下命令（将 `<YOUR_TOKEN>` 替换为你的 Personal Access Token）：

```bash
cd /home/biochm/Reagent-manager
git remote set-url origin https://<YOUR_TOKEN>@github.com/Peaktailing/BCLRM.git
git push -u origin main
```

### 如果你选择方案二（SSH）
```bash
cd /home/biochm/Reagent-manager

# 先生成 SSH 密钥
ssh-keygen -t ed25519 -C "your_email@example.com"

# 复制公钥
cat ~/.ssh/id_ed25519.pub

# 在 GitHub 添加公钥后，执行：
git remote set-url origin git@github.com:Peaktailing/BCLRM.git
ssh -T git@github.com
git push -u origin main
```

## 注意事项

⚠️ **Token 安全**：不要将 Personal Access Token 提交到代码中
⚠️ **SSH 密钥**：保护好私钥，不要泄露
⚠️ **权限**：确保你对该仓库有 push 权限

## 验证配置

完成配置后，验证是否成功：

```bash
git remote -v
# 应该显示：
# origin  https://github.com/Peaktailing/BCLRM.git (fetch)
# origin  https://github.com/Peaktailing/BCLRM.git (push)
# 或 SSH 格式
# origin  git@github.com:Peaktailing/BCLRM.git (fetch)
# origin  git@github.com:Peaktailing/BCLRM.git (push)

git log --oneline
# 应该显示你的提交记录
```

## 获取帮助

如果遇到问题，查看错误信息并参考：
- GitHub 官方文档：https://docs.github.com/
- Git 官方文档：https://git-scm.com/doc
