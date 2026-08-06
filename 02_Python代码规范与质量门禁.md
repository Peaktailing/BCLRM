# Python 代码规范与质量门禁（BCLRM 团队版）

> 目的：把"资深把关"沉淀成团队可执行的标准。所有规则都要能机器校验（CI 卡住），而不是靠 review 时人工挑刺。
> 适用栈：Python 3.10+ / Streamlit / SQLite / Pydantic v2
> 配套文件：`configs/pyproject.toml`、`configs/.pre-commit-config.yaml`、`configs/ci.yml`

---

## 一、目录与分层约定（先统一心智模型）

```
BCLRM/
├── db/            # 数据访问层（DAL）：连接管理、BaseService、迁移。禁止写业务逻辑。
├── models/        # Pydantic 模型（贫血的数据契约）。禁止 import streamlit。
├── services/      # 业务服务层：组合 models + db，封装业务规则。可注入 db 便于测试。
├── business/      # 跨服务的用例编排（如"入库"流程）。
├── components/    # Streamlit 组件 / 认证 / 导航（只许这一层 import streamlit）。
├── pages/         # Streamlit 页面（纯 UI 编排，尽量薄）。
├── config/        # 配置常量，单一事实来源（含 VERSION）。
├── utils/         # 无状态工具（密码、ID、日志）。
└── tests/         # 全部测试集中此处，pytest 发现。
```

**依赖方向**：`pages → components → business → services → db/models`，**禁止反向**。任何层 import `streamlit` 都只允许在 `components/` 与 `pages/`。

---

## 二、编码规范（ruff 自动执行）

| 维度 | 规则 |
|------|------|
| 行宽 | 100 字符 |
| 引号 | 双引号 `"` |
| 导入 | 自动排序（isort/I）、禁止无用导入（F401） |
| 命名 | 函数/变量 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE` |
| 类型 | 新代码**必须**有类型注解；开启 `mypy` 严格度 `warn_return_any` |
| 字符串格式化 | 优先 f-string，日志用结构化参数而非拼接 |
| 文件命名 | 测试必须是 `test_*.py`；**禁止** `test.py` 这种会被误收集的名字 |
| 遗留代码 | `sys.path.insert` 脏注入一律删除，靠安装包解决 |

Ruff 启用的规则集（建议在 `pyproject.toml` 固定）：`E,F,W,I,B,C4,UP,SIM,RUF`（基础 + bug-risk + 现代化 + 简化）。

---

## 三、数据库访问铁律（本项目最高频的坑）

1. **值必须参数化**：`cursor.execute("... WHERE x = ?", (val,))`，禁止 f-string 拼值。
2. **标识符（表名/列名/排序）必须白名单校验**：沿用现有 `_FIELD_NAME_PATTERN` / `_ORDER_BY_PATTERN` 正则——这是项目已有且做对的，固化成规范。
3. **禁止吞异常**：`BaseService` 的数据访问方法**不得** `except: return []/None`。出错就抛（或返回显式 `Result` 失败），让上层决定如何展示。**（修复 H1）**
4. **跨表操作必须事务化**：提供 `with db.transaction():` 上下文管理器，多表写要么全成要么全败。**（修复 M4）**
5. **连接线程安全**：SQLite 单连接共享必须加锁，或改为每请求/每线程连接。**（修复 H2）**
6. **`updated_at` 必须可更新**：用 `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP` 必须配套 `ON UPDATE` 触发器或应用层赋值，否则该字段是谎言。**（修复 M3）**
7. **运行时数据永不入库**：`*.db`、`*-wal`、`*-shm`、`db_wal/`、`attachments/`、`logs/`、`.uploads/` 全部 gitignore；数据库只提交**建表 SQL/迁移脚本**，数据靠初始化/种子脚本生成。**（修复 M2）**
8. **状态用枚举/布尔**：`borrowable_flag` 这类中文字符串改为 `bool` 或 `Enum`。**（修复 M5）**
9. **多值关系用关联表**：`reagent_type` 的逗号分隔改为 junction table。**（修复 M6）**

---

## 四、错误处理规范

- 业务失败用**显式结果对象**（`Result`/现有 `is_success()` 模式），不要用异常当控制流，也不要用 `return None` 掩盖。
- 日志：生产错误只记"发生了什么 + 参数类型数量"，**绝不记参数值**（已做的脱敏实践保留）。
- 对外（UI/API）错误信息要友好且**不泄露内部结构**（系统设置页的 `st.error` 不暴露原始异常——已做，保留）。

---

## 五、安全规范

- 密码：PBKDF2-HMAC-SHA256（已做），迭代次数集中常量管理。
- 认证失败返回**统一**文案，不区分"用户不存在/密码错"（消除用户名枚举，L5）。
- 登录加失败次数限制/锁死（L6）。
- 密钥/密码放 `.env` 或 `.streamlit/secrets.toml`，**已 gitignore**，持续保持。
- 所有页面强制 `require_auth()`，管理员操作加 `require_admin()`/`require_super_admin()`（已做，保持）。

---

## 六、测试规范

- 框架：统一 **pytest**（现有 48 个 unittest 可逐步迁移，不强制一步到位）。
- 组织：全部置于 `tests/`，文件名 `test_*.py`。
- 层级：
  - 单元测试：纯函数/模型/工具，用 `tmp_path` 建临时库，不碰真实数据。
  - 集成测试：Service 层注入测试库（现有 `_setup_service` 思路保留并简化）。
- 覆盖目标：核心业务（入库/领用/归还/权限）必须覆盖；CI 设**覆盖率门槛**（例如 ≥70%，逐步提升）。
- 禁止测试依赖仓库内真实 `*.db`。

---

## 七、质量门禁（CI 卡死，PR 不达标不许合）

| 门禁 | 工具 | 失败即阻断 |
|------|------|-----------|
| 代码风格/lint | `ruff check .` | ✅ |
| 格式化 | `ruff format --check .` | ✅ |
| 类型 | `mypy db services models business components utils config` | ✅ |
| 测试 | `pytest`（含覆盖率门槛） | ✅ |
| 大文件 | pre-commit `check-added-large-files`（>500KB 拒绝，防 DB 文件入仓） | ✅ |
| 合并冲突标记 | pre-commit `check-merge-conflict` | ✅ |

---

## 八、PR 评审清单（每次合并前自查 + reviewer 勾选）

- [ ] 新代码有类型注解，通过 `mypy`
- [ ] 通过 `ruff` 检查与格式化
- [ ] 所有 DB 值参数化，标识符经白名单校验
- [ ] 跨表写操作包在事务里
- [ ] 异常未被静默吞掉（无 `return []/None` 掩盖错误）
- [ ] 新增/修改有对应测试，CI 全绿
- [ ] 未提交任何 `*.db` / 密钥 / 大文件
- [ ] 未引入 `sys.path` 脏注入
- [ ] 安全相关改动（认证/权限）已双人确认

---

## 九、依赖与构建（解决 L2）

- 弃用 `setup.py` + `requirements.txt` 双轨，统一到 `pyproject.toml` 的 `[project]`。
- 生产依赖锁版本（用 `pip-tools` 生成 `requirements.lock` 或 `uv lock`），保证可复现。
- 开发依赖（ruff/mypy/pytest/pytest-cov）放 `[project.optional-dependencies].dev`。
