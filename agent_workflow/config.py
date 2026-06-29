"""Agent 角色配置与模型分配

基于开发基础文档，定义5个角色及其职责范围、模型分配。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict


class AgentRole(Enum):
    """Agent 角色枚举"""
    MAIN = "main"           # 主 Agent - 对话沟通 & 架构协调
    BACKEND = "backend"     # 后端 Agent - 业务逻辑 / ORM / 数据库
    FRONTEND = "frontend"   # 前端 Agent - Streamlit 页面 / 组件
    TEST = "test"           # 测试 & 复核 Agent - 代码审查 / 测试
    CONTEXT = "context"     # 超长上下文 Agent - 全量文档把控


@dataclass
class RoleConfig:
    """单个角色的详细配置"""
    role: AgentRole
    display_name: str
    model: str                          # 分配的 LLM 模型
    description: str                    # 角色职责描述
    # 该角色负责的项目文件/目录（相对于项目根目录）
    responsible_paths: List[str] = field(default_factory=list)
    # 该角色禁止操作的文件/目录
    forbidden_paths: List[str] = field(default_factory=list)
    # 角色需要预加载的上下文文件
    context_files: List[str] = field(default_factory=list)
    # 角色优先级（数字越小优先级越高，用于任务分发时的决策）
    priority: int = 10


class WorkflowConfig:
    """工作流全局配置

    角色分配：
    - 主 Agent: DeepSeek — 负责对话沟通、架构设计、任务分发
    - 后端 Agent: DeepSeek — 负责 Python 业务逻辑、ORM 服务、数据库层
    - 前端 Agent: GLM — 负责 Streamlit 页面、UI 组件
    - 测试 Agent: Qwen — 负责代码审查、测试验证、复核
    - 上下文 Agent: Kimi — 负责超长上下文把控、文档一致性检查
    """

    # 系统提示词（全局共用）
    SYSTEM_PROMPT = """你是一个多角色协作开发 Agent 系统中的一员。
请严格遵循以下规则：
1. 只处理你角色职责范围内的任务，不要越权操作其他角色的文件
2. 每次修改代码前，必须先阅读 docs/开发基础文档.md 和 docs/业务流转逻辑.md
3. 后端代码遵循面向对象 Class 开发范式，禁止过程式脚本写法
4. 所有修改必须通过统一编排器提交，最终由主 Agent 审核合并
5. 遇到不确定的问题，标记为「待确认」并回传给主 Agent"""

    # ----- 角色定义 -----
    ROLES: Dict[AgentRole, RoleConfig] = {
        AgentRole.MAIN: RoleConfig(
            role=AgentRole.MAIN,
            display_name="主 Agent (架构师)",
            model="deepseek-chat",
            description="负责与用户对话沟通、理解需求、设计整体架构方案、将任务拆解分发给各子 Agent、最终审核合并代码",
            responsible_paths=[
                "app.py",
                "requirements.txt",
                "config/",
                "docs/",
                "README.md",
                ".gitignore",
            ],
            forbidden_paths=[
                # 主 Agent 不直接修改具体业务代码，只做架构和配置
                "business/",
                "services/",
                "models/",
                "pages/",
                "components/",
                "utils/",
            ],
            context_files=[
                "docs/开发基础文档.md",
                "docs/业务流转逻辑.md",
                "docs/更新日志.md",
                "docs/部署说明.md",
            ],
            priority=1,  # 最高优先级
        ),
        AgentRole.BACKEND: RoleConfig(
            role=AgentRole.BACKEND,
            display_name="后端 Agent (DeepSeek)",
            model="deepseek-chat",
            description="负责后端 Python 代码开发：业务逻辑层 (business/)、ORM 服务层 (services/)、数据模型层 (models/)、数据库访问层 (db/)、工具函数 (utils/)",
            responsible_paths=[
                "business/",
                "services/",
                "models/",
                "db/",
                "utils/",
                "scripts/",
            ],
            forbidden_paths=[
                "pages/",
                "components/",
                "login-frontend/",
            ],
            context_files=[
                "docs/开发基础文档.md",
                "docs/业务流转逻辑.md",
                "db/base_service.py",
                "db/database.py",
                "utils/error_handler.py",
            ],
            priority=2,
        ),
        AgentRole.FRONTEND: RoleConfig(
            role=AgentRole.FRONTEND,
            display_name="前端 Agent (GLM)",
            model="glm-4",
            description="负责前端 UI 开发：Streamlit 页面 (pages/)、可复用组件 (components/)、页面交互逻辑、数据展示",
            responsible_paths=[
                "pages/",
                "components/",
            ],
            forbidden_paths=[
                "business/",
                "services/",
                "models/",
                "db/",
                "utils/",
                "scripts/",
                "config/",
            ],
            context_files=[
                "docs/开发基础文档.md",
                "docs/用户使用手册.md",
                "components/base_table.py",
                "components/base_form.py",
                "components/sidebar_nav.py",
                "components/status_badge.py",
            ],
            priority=3,
        ),
        AgentRole.TEST: RoleConfig(
            role=AgentRole.TEST,
            display_name="测试 & 复核 Agent (Qwen)",
            model="qwen-max",
            description="负责代码审查 (Code Review)、测试用例编写与执行、代码质量检查、规范符合性验证、最终复核",
            responsible_paths=[
                "test.py",
                "test_db_connection.py",
                # 代码审查时可读取所有文件
            ],
            forbidden_paths=[
                # 测试 Agent 不应直接修改业务代码，只标记问题
            ],
            context_files=[
                "docs/开发基础文档.md",
                "docs/业务流转逻辑.md",
                "docs/更新日志.md",
                "VERIFICATION_REPORT.md",
            ],
            priority=4,
        ),
        AgentRole.CONTEXT: RoleConfig(
            role=AgentRole.CONTEXT,
            display_name="上下文 Agent (Kimi)",
            model="kimi",
            description="负责超长上下文把控：阅读全量文档确保一致性、检查跨文件引用正确性、当代码库过大时提供上下文摘要、确保各角色产出与开发文档一致",
            responsible_paths=[
                "docs/",
                # 上下文 Agent 可读取全项目文件，但只做上下文分析和一致性检查
            ],
            forbidden_paths=[
                # 上下文 Agent 不直接修改代码，只提供分析报告
            ],
            context_files=[
                "docs/开发基础文档.md",
                "docs/业务流转逻辑.md",
                "docs/更新日志.md",
                "docs/部署说明.md",
                "docs/用户使用手册.md",
                "docs/GITHUB_AUTH.md",
                "docs/GIT_SETUP.md",
            ],
            priority=5,
        ),
    }

    # 工作流阶段定义
    WORKFLOW_STAGES = [
        "需求分析",      # 主 Agent 理解需求，查阅文档
        "架构设计",      # 主 Agent 设计实现方案，拆解任务
        "上下文检查",    # 上下文 Agent 检查文档一致性
        "后端开发",      # 后端 Agent 实现业务逻辑
        "前端开发",      # 前端 Agent 实现页面
        "代码审查",      # 测试 Agent 审查代码质量
        "测试验证",      # 测试 Agent 执行测试
        "上下文复核",    # 上下文 Agent 最终一致性检查
        "合并提交",      # 主 Agent 审核合并，提交代码
    ]

    @classmethod
    def get_role_config(cls, role: AgentRole) -> RoleConfig:
        """获取指定角色的配置"""
        return cls.ROLES[role]

    @classmethod
    def get_model_for_role(cls, role: AgentRole) -> str:
        """获取指定角色使用的模型"""
        return cls.ROLES[role].model

    @classmethod
    def get_all_roles(cls) -> List[AgentRole]:
        """获取所有角色列表"""
        return list(cls.ROLES.keys())

    @classmethod
    def get_role_by_model(cls, model: str) -> List[AgentRole]:
        """根据模型名查找使用该模型的所有角色"""
        return [role for role, cfg in cls.ROLES.items() if cfg.model == model]