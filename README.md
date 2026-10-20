# BCLRM 生化实验室试剂管理系统

一个面向生物-化学实验室的试剂全生命周期管理系统，基于 **Python + Streamlit + SQLite**，由 Trae cn 发起、持续迭代定制。目标是快速部署、按实验室实际流程灵活演进。

当前版本：**v0.8.15**（更新明细见 [docs/更新日志.md](docs/更新日志.md)；本次审核修复说明见 [docs/修复说明_2026-10-20.md](docs/修复说明_2026-10-20.md)）

## 功能总览

| 模块 | 说明 |
| --- | --- |
| 实时库存 | 试剂瓶状态（可借/已借出/耗尽/已过期）、条码扫码查询、管理人展示 |
| 试剂入库 | 单瓶入库 + 按采购单批量入库；入库时指定管理人（保管权归属） |
| 领用归还 | 工单制领用（零星/课程，手动指定管理员审批人）、管控试剂审批、撤回与应急重新指定审批人、按工单逐瓶归还（比例滑块，空瓶原子进待报废） |
| 需求调配 | 提交需求 → 智能分配（本人 → 本教研室 → 全院）→ 按管理人拆分调配单 → 借出/退回 |
| 管理权流转 | 试剂保管权在管理员间多选批量流转，逐瓶记录变更历史 |
| 试剂处置 | 待报废清单、过期预警、管理权流转 |
| 采购管理 | 课程采购单生成/提交、汇总采购单（含已批准预定单）、预定单审批、采购跟踪（取消/下单/到货/入库） |
| 综合查询 / 数据看板 / 学期用量 | 多条件查询、统计报表、按「课程-实验-试剂」维度统计人均用量 |
| 课程管理 | 分组表导入、实验项目去重、默认实验方案与人均用量 |
| 化学品信息 / 管控目录 | 化学品档案（多类型标签、有效期）、管控化学品名录 |
| 系统设置 | 用户与角色管理、数据库数据查看（仅超级管理员） |

## 快速开始

```bash
# 1. 安装依赖（建议 Python 3.10+，使用虚拟环境）
pip install -r requirements.txt

# 2. 初始化数据库（自动建表与迁移）
python scripts/init_db.py

# 3. 启动
streamlit run app.py
```

- 数据库为本地 SQLite（`db/` 目录），**已加入 .gitignore，不会上传**。
- 新建用户初始密码为迁移期默认密码，首次登录后请尽快修改。

## 目录结构

```
app.py               # 入口（st.navigation 多页面路由）+ 品牌换肤 apply_theme()
views/               # Streamlit 页面（每页一个文件）
components/          # 认证、侧边栏、品牌主题（theme.py 注入 assets/design 样式）
assets/design/       # 设计 token（tokens.css）与 Streamlit 换肤层（streamlit.css）
business/            # 业务服务层（领用、采购、调配、审批等）
services/            # 数据服务层（继承 BaseService，统一 CRUD 与标识符校验）
models/              # 数据模型（dataclass / pydantic）
db/                  # SQLite 封装（单例、事务、建表与迁移）
utils/               # 字段常量、编号生成、密码、审计等工具
docs/                # 使用手册、更新日志、业务流转、评审文档
docs/design_mockups/ # 设计包原稿（9 个 HTML 页面，品牌样式的视觉依据）
scripts/             # 初始化、导入等离线脚本
```

## 品牌样式

- 主色 `#E1251B`、侧边栏深灰 `#1D2129`，token 唯一来源：`assets/design/tokens.css`
- Streamlit 原生主题参数在 `.streamlit/config.toml`（改完需重启应用生效）
- DOM 级换肤在 `assets/design/streamlit.css`（改完刷新页面即生效），由 `components/theme.py` 注入
- 页面里需要状态徽标时用 `from components.theme import badge`，配合 `st.markdown(..., unsafe_allow_html=True)`

## 安全设计要点

- 密码：PBKDF2-HMAC-SHA256（600k 迭代 + 盐），常量时间比较
- SQL：全部参数化；动态表名/字段名/ORDER BY 经正则白名单校验
- 审计：关键操作写入操作日志，日志参数脱敏
- 页面级认证：全部页面 `require_auth()`；未注册页面不可 URL 直达

## 文档

- [用户使用手册](docs/用户使用手册.md)
- [更新日志](docs/更新日志.md)
- [BUG 修复报告](docs/BUG修复报告.md)
- [业务流转逻辑](docs/业务流转逻辑.md)
- [开发基础文档](docs/开发基础文档.md)
- [三方协作手册](docs/三方协作手册.md)（Trae / Qoder / CodeBuddy 并行维护约定）
