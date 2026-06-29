"""预定义工作流模板 - 基于开发基础文档的协作流程

定义了常见开发场景的标准化工作流，每个场景指定了参与的角色、阶段和任务分配。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .config import AgentRole


class WorkflowType(Enum):
    """预定义工作流类型"""
    # 新增功能
    FEATURE_BACKEND = "feature_backend"         # 纯后端新功能
    FEATURE_FRONTEND = "feature_frontend"       # 纯前端新功能
    FEATURE_FULLSTACK = "feature_fullstack"     # 全栈新功能（前后端都涉及）
    
    # Bug 修复
    BUG_FIX = "bug_fix"                         # Bug 修复
    
    # 代码重构
    REFACTOR = "refactor"                       # 代码重构
    
    # 文档更新
    DOCS_UPDATE = "docs_update"                 # 文档更新
    
    # 代码审查
    CODE_REVIEW = "code_review"                 # 代码审查（不修改）
    
    # 测试
    TEST = "test"                               # 测试验证
    
    # 架构调整
    ARCHITECTURE_CHANGE = "architecture_change" # 架构变更


@dataclass
class WorkflowTask:
    """预定义工作流中的单个任务定义"""
    name: str
    role: AgentRole
    description: str
    # 该任务需要关注的文件（用于提示 Agent）
    target_files: List[str] = field(default_factory=list)
    # 该任务的上下文提示
    context_hint: str = ""
    # 该任务依赖的前置任务（name 列表）
    depends_on: List[str] = field(default_factory=list)


# ============================================================
# 预定义工作流模板
# ============================================================

class WorkflowTemplates:
    """基于开发基础文档的预定义工作流模板"""

    # ---------- 全栈新功能开发 ----------
    FEATURE_FULLSTACK = [
        WorkflowTask(
            name="需求分析",
            role=AgentRole.MAIN,
            description="分析需求，查阅开发基础文档，确定涉及的文件和层级",
            target_files=["docs/开发基础文档.md", "docs/业务流转逻辑.md"],
            context_hint="先阅读开发基础文档，确认需求涉及哪些层级（模型/服务/业务/页面）",
        ),
        WorkflowTask(
            name="上下文检查",
            role=AgentRole.CONTEXT,
            description="检查现有文档与代码结构一致性，确保新功能不破坏现有架构",
            target_files=["docs/"],
            context_hint="检查开发文档中提到的所有目录和文件是否存在，确认架构一致性",
            depends_on=["需求分析"],
        ),
        WorkflowTask(
            name="后端开发-模型层",
            role=AgentRole.BACKEND,
            description="定义新的 dataclass 实体类，确保与数据库表结构对应",
            target_files=["models/"],
            context_hint="使用 @dataclass 定义实体类，字段类型统一声明，禁止裸字典传输",
            depends_on=["上下文检查"],
        ),
        WorkflowTask(
            name="后端开发-服务层",
            role=AgentRole.BACKEND,
            description="实现 ORM 服务类，继承 BaseService，封装单表 CRUD",
            target_files=["services/"],
            context_hint="继承 db/base_service.py，封装单表增删改查，不承载业务规则",
            depends_on=["后端开发-模型层"],
        ),
        WorkflowTask(
            name="后端开发-业务层",
            role=AgentRole.BACKEND,
            description="实现业务逻辑类，包含数据校验、流程控制、状态计算",
            target_files=["business/"],
            context_hint="所有业务规则唯一实现地，返回 ServiceResult 对象，禁止 Streamlit 代码",
            depends_on=["后端开发-服务层"],
        ),
        WorkflowTask(
            name="前端开发-页面",
            role=AgentRole.FRONTEND,
            description="实现 Streamlit 页面，只负责 UI 渲染和调用业务层方法",
            target_files=["pages/"],
            context_hint="只写 st.xxx 组件，调用 business 层类方法，禁止直接操作数据库",
            depends_on=["后端开发-业务层"],
        ),
        WorkflowTask(
            name="前端开发-组件",
            role=AgentRole.FRONTEND,
            description="实现或复用通用 UI 组件（表格、表单、导航等）",
            target_files=["components/"],
            context_hint="复用现有组件，新增组件需封装为类",
            depends_on=["前端开发-页面"],
        ),
        WorkflowTask(
            name="代码审查",
            role=AgentRole.TEST,
            description="审查所有修改的代码，检查规范符合性",
            target_files=[],
            context_hint="检查：命名规范、缩进、类封装、禁止裸字典、禁止裸except、禁止硬编码",
            depends_on=["前端开发-页面", "后端开发-业务层"],
        ),
        WorkflowTask(
            name="上下文复核",
            role=AgentRole.CONTEXT,
            description="最终检查修改后的代码与文档是否一致",
            target_files=["docs/"],
            context_hint="确认修改后的代码与开发基础文档规范一致，更新变更日志",
            depends_on=["代码审查"],
        ),
        WorkflowTask(
            name="更新文档",
            role=AgentRole.MAIN,
            description="更新开发基础文档和更新日志",
            target_files=["docs/开发基础文档.md", "docs/更新日志.md"],
            context_hint="按照文档更新模板更新变更日志，更新功能对照表",
            depends_on=["上下文复核"],
        ),
        WorkflowTask(
            name="审核合并",
            role=AgentRole.MAIN,
            description="审核所有结果，合并代码，执行 Git 提交",
            target_files=[],
            context_hint="按照 Git 提交规范统一提交，格式: feat: 描述",
            depends_on=["更新文档"],
        ),
    ]

    # ---------- 纯后端新功能 ----------
    FEATURE_BACKEND = [
        WorkflowTask(
            name="需求分析",
            role=AgentRole.MAIN,
            description="分析需求，确定涉及的后端层级",
            target_files=["docs/开发基础文档.md", "docs/业务流转逻辑.md"],
            context_hint="",
        ),
        WorkflowTask(
            name="后端开发",
            role=AgentRole.BACKEND,
            description="实现 models → services → business 三层后端代码",
            target_files=["models/", "services/", "business/"],
            context_hint="按 models → services → business 顺序开发，确保类名和引用正确",
            depends_on=["需求分析"],
        ),
        WorkflowTask(
            name="代码审查",
            role=AgentRole.TEST,
            description="审查后端代码规范和架构合规性",
            target_files=[],
            context_hint="",
            depends_on=["后端开发"],
        ),
        WorkflowTask(
            name="审核合并",
            role=AgentRole.MAIN,
            description="审核并合并代码",
            target_files=[],
            context_hint="",
            depends_on=["代码审查"],
        ),
    ]

    # ---------- 纯前端新功能 ----------
    FEATURE_FRONTEND = [
        WorkflowTask(
            name="需求分析",
            role=AgentRole.MAIN,
            description="分析前端需求，确认使用的业务层接口",
            target_files=["docs/开发基础文档.md", "docs/用户使用手册.md"],
            context_hint="确认前端页面需要调用哪些 business 层方法",
        ),
        WorkflowTask(
            name="前端开发",
            role=AgentRole.FRONTEND,
            description="实现 Streamlit 页面和组件",
            target_files=["pages/", "components/"],
            context_hint="只写 UI 渲染，调用 business 层方法，禁止直接操作数据库",
            depends_on=["需求分析"],
        ),
        WorkflowTask(
            name="代码审查",
            role=AgentRole.TEST,
            description="审查前端代码规范",
            target_files=[],
            context_hint="检查页面层是否包含业务逻辑、是否直接操作数据库",
            depends_on=["前端开发"],
        ),
        WorkflowTask(
            name="审核合并",
            role=AgentRole.MAIN,
            description="审核并合并代码",
            target_files=[],
            context_hint="",
            depends_on=["代码审查"],
        ),
    ]

    # ---------- Bug 修复 ----------
    BUG_FIX = [
        WorkflowTask(
            name="问题定位",
            role=AgentRole.MAIN,
            description="根据用户描述定位问题文件（参考功能对照表）",
            target_files=["docs/开发基础文档.md"],
            context_hint="参考功能-文件对照表快速定位问题所在文件",
        ),
        WorkflowTask(
            name="上下文检查",
            role=AgentRole.CONTEXT,
            description="检查相关文档，确认 Bug 原因是否与架构不一致有关",
            target_files=["docs/"],
            context_hint="",
            depends_on=["问题定位"],
        ),
        WorkflowTask(
            name="修复代码",
            role=AgentRole.BACKEND,
            description="修复后端代码 Bug",
            target_files=[],
            context_hint="修复前先确认文件层级职责，确保修复不破坏架构规范",
            depends_on=["上下文检查"],
        ),
        WorkflowTask(
            name="代码审查",
            role=AgentRole.TEST,
            description="审查修复代码，检查是否引入新问题",
            target_files=[],
            context_hint="",
            depends_on=["修复代码"],
        ),
        WorkflowTask(
            name="审核合并",
            role=AgentRole.MAIN,
            description="审核并合并修复代码",
            target_files=[],
            context_hint="按照 Git 提交规范: fix: 描述",
            depends_on=["代码审查"],
        ),
    ]

    # ---------- 代码重构 ----------
    REFACTOR = [
        WorkflowTask(
            name="架构分析",
            role=AgentRole.MAIN,
            description="分析重构范围，确定影响范围",
            target_files=["docs/开发基础文档.md"],
            context_hint="确认重构涉及的所有层级，评估影响范围",
        ),
        WorkflowTask(
            name="上下文检查",
            role=AgentRole.CONTEXT,
            description="全量文档一致性检查，确保重构不破坏架构",
            target_files=["docs/"],
            context_hint="检查所有跨文件引用，确保重构后引用保持一致",
            depends_on=["架构分析"],
        ),
        WorkflowTask(
            name="执行重构",
            role=AgentRole.BACKEND,
            description="执行后端代码重构",
            target_files=[],
            context_hint="严格遵循开发规范：面向对象Class、命名规范、层级分离",
            depends_on=["上下文检查"],
        ),
        WorkflowTask(
            name="代码审查",
            role=AgentRole.TEST,
            description="全面审查重构代码",
            target_files=[],
            context_hint="检查重构是否引入新问题，是否保持原有功能",
            depends_on=["执行重构"],
        ),
        WorkflowTask(
            name="上下文复核",
            role=AgentRole.CONTEXT,
            description="最终一致性检查",
            target_files=["docs/"],
            context_hint="",
            depends_on=["代码审查"],
        ),
        WorkflowTask(
            name="审核合并",
            role=AgentRole.MAIN,
            description="审核并合并重构代码",
            target_files=[],
            context_hint="按照 Git 提交规范: refactor: 描述",
            depends_on=["上下文复核"],
        ),
    ]

    # ---------- 文档更新 ----------
    DOCS_UPDATE = [
        WorkflowTask(
            name="文档分析",
            role=AgentRole.MAIN,
            description="分析需要更新的文档范围",
            target_files=["docs/"],
            context_hint="",
        ),
        WorkflowTask(
            name="更新文档",
            role=AgentRole.MAIN,
            description="更新开发基础文档和用户手册",
            target_files=["docs/开发基础文档.md", "docs/用户使用手册.md", "docs/更新日志.md"],
            context_hint="按照更新日志模板更新",
            depends_on=["文档分析"],
        ),
        WorkflowTask(
            name="上下文复核",
            role=AgentRole.CONTEXT,
            description="检查文档更新后的一致性",
            target_files=["docs/"],
            context_hint="",
            depends_on=["更新文档"],
        ),
        WorkflowTask(
            name="审核合并",
            role=AgentRole.MAIN,
            description="审核并提交文档更新",
            target_files=[],
            context_hint="按照 Git 提交规范: docs: 描述",
            depends_on=["上下文复核"],
        ),
    ]

    # ---------- 代码审查（不修改） ----------
    CODE_REVIEW = [
        WorkflowTask(
            name="上下文加载",
            role=AgentRole.CONTEXT,
            description="加载全量文档和代码上下文",
            target_files=["docs/", "models/", "services/", "business/", "pages/"],
            context_hint="提供全项目上下文摘要",
        ),
        WorkflowTask(
            name="代码审查",
            role=AgentRole.TEST,
            description="全面审查代码质量和规范",
            target_files=[],
            context_hint="检查：命名规范、缩进、类封装、禁止裸字典、禁止裸except、禁止硬编码、层级分离",
            depends_on=["上下文加载"],
        ),
        WorkflowTask(
            name="输出报告",
            role=AgentRole.MAIN,
            description="整理审查结果，输出审查报告",
            target_files=[],
            context_hint="",
            depends_on=["代码审查"],
        ),
    ]

    # ---------- 架构变更 ----------
    ARCHITECTURE_CHANGE = [
        WorkflowTask(
            name="架构分析",
            role=AgentRole.MAIN,
            description="分析架构变更需求和影响范围",
            target_files=["docs/开发基础文档.md"],
            context_hint="架构变更需谨慎评估影响范围",
        ),
        WorkflowTask(
            name="全量上下文检查",
            role=AgentRole.CONTEXT,
            description="Kimi 加载全量文档，分析变更影响",
            target_files=["docs/", "models/", "services/", "business/", "pages/", "components/"],
            context_hint="全量分析所有受影响文件，列出变更清单",
            depends_on=["架构分析"],
        ),
        WorkflowTask(
            name="后端变更",
            role=AgentRole.BACKEND,
            description="执行后端架构变更",
            target_files=[],
            context_hint="",
            depends_on=["全量上下文检查"],
        ),
        WorkflowTask(
            name="前端变更",
            role=AgentRole.FRONTEND,
            description="同步前端架构变更",
            target_files=[],
            context_hint="",
            depends_on=["后端变更"],
        ),
        WorkflowTask(
            name="代码审查",
            role=AgentRole.TEST,
            description="全面审查变更代码",
            target_files=[],
            context_hint="",
            depends_on=["前端变更"],
        ),
        WorkflowTask(
            name="上下文复核",
            role=AgentRole.CONTEXT,
            description="最终一致性检查",
            target_files=["docs/"],
            context_hint="",
            depends_on=["代码审查"],
        ),
        WorkflowTask(
            name="更新文档",
            role=AgentRole.MAIN,
            description="同步更新开发文档",
            target_files=["docs/开发基础文档.md", "docs/更新日志.md"],
            context_hint="",
            depends_on=["上下文复核"],
        ),
        WorkflowTask(
            name="审核合并",
            role=AgentRole.MAIN,
            description="审核并合并架构变更",
            target_files=[],
            context_hint="",
            depends_on=["更新文档"],
        ),
    ]

    # 工作流类型到模板的映射
    TEMPLATES: Dict[WorkflowType, List[WorkflowTask]] = {
        WorkflowType.FEATURE_FULLSTACK: FEATURE_FULLSTACK,
        WorkflowType.FEATURE_BACKEND: FEATURE_BACKEND,
        WorkflowType.FEATURE_FRONTEND: FEATURE_FRONTEND,
        WorkflowType.BUG_FIX: BUG_FIX,
        WorkflowType.REFACTOR: REFACTOR,
        WorkflowType.DOCS_UPDATE: DOCS_UPDATE,
        WorkflowType.CODE_REVIEW: CODE_REVIEW,
        WorkflowType.ARCHITECTURE_CHANGE: ARCHITECTURE_CHANGE,
    }

    @classmethod
    def get_template(cls, workflow_type: WorkflowType) -> List[WorkflowTask]:
        """获取指定类型的工作流模板"""
        return cls.TEMPLATES.get(workflow_type, cls.FEATURE_FULLSTACK)

    @classmethod
    def get_all_types(cls) -> List[WorkflowType]:
        """获取所有可用工作流类型"""
        return list(cls.TEMPLATES.keys())