"""Agent 基类和各角色具体实现

每个角色定义了独立的任务接口，负责执行其职责范围内的开发工作。
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

from .config import AgentRole, RoleConfig, WorkflowConfig


@dataclass
class AgentTask:
    """Agent 接收的单个任务"""
    task_id: str
    description: str
    files: List[str]              # 需要修改/检查的文件路径列表（相对于项目根）
    context: str                  # 上下文信息（需求描述、已有代码说明等）
    role: AgentRole               # 分配给哪个角色
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Agent 执行任务返回的结果"""
    task_id: str
    success: bool
    message: str                  # 执行结果说明
    modified_files: List[str] = field(default_factory=list)  # 修改过的文件
    issues_found: List[str] = field(default_factory=list)    # 发现的问题
    suggestions: List[str] = field(default_factory=list)     # 修改建议
    output_data: Optional[Dict[str, Any]] = None
    needs_review: bool = False
    pending_confirmation: bool = False  # 是否需要向用户确认
    confirmation_question: Optional[str] = None  # 需要确认的问题


class AgentBase(ABC):
    """所有 Agent 的基类"""

    def __init__(self, role_config: RoleConfig, project_root: str = "."):
        self.role_config = role_config
        self.project_root = Path(project_root).resolve()
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """构建 Agent 的系统提示词"""
        base_prompt = WorkflowConfig.SYSTEM_PROMPT
        role_prompt = f"""
你的角色是：{self.role_config.display_name}
你的职责：{self.role_config.description}

你负责以下路径：
{chr(10).join('- ' + path for path in self.role_config.responsible_paths)}

你禁止操作以下路径：
{chr(10).join('- ' + path for path in self.role_config.forbidden_paths) if self.role_config.forbidden_paths else '（无）'}
"""
        # 添加开发文档提示
        doc_path = self.project_root / "docs" / "开发基础文档.md"
        if doc_path.exists():
            role_prompt += f"\n项目开发规范以 {doc_path} 为准，必须严格遵守。\n"

        return base_prompt + "\n" + role_prompt

    def get_absolute_path(self, relative_path: str) -> Path:
        """获取相对于项目根的绝对路径"""
        return self.project_root / relative_path.lstrip('/')

    def is_path_allowed(self, path: str) -> bool:
        """检查路径是否允许该 Agent 修改"""
        # 绝对路径转相对
        abs_path = Path(path).resolve()
        rel_path = str(abs_path.relative_to(self.project_root))

        # 检查禁止路径
        for forbidden in self.role_config.forbidden_paths:
            if rel_path.startswith(forbidden):
                return False

        # 如果负责任务为空，允许所有未禁止的路径
        if not self.role_config.responsible_paths:
            return True

        # 检查负责任务
        for allowed in self.role_config.responsible_paths:
            if rel_path.startswith(allowed):
                return True

        return False

    def preload_context_files(self) -> str:
        """预加载角色相关的上下文文件内容"""
        context = ""
        for f in self.role_config.context_files:
            file_path = self.get_absolute_path(f)
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as fobj:
                    content = fobj.read()
                    context += f"\n\n--- {f} ---\n{content}\n"
        return context

    @abstractmethod
    def execute(self, task: AgentTask) -> AgentResult:
        """执行分配的任务，返回结果"""
        pass


class MainAgent(AgentBase):
    """主 Agent - DeepSeek

    职责：
    - 与用户对话沟通，理解需求
    - 设计整体架构方案
    - 将任务拆解分发给各子 Agent
    - 最终审核合并代码
    - Git 提交
    """

    def __init__(self, project_root: str = "."):
        config = WorkflowConfig.get_role_config(AgentRole.MAIN)
        super().__init__(config, project_root)
        self.model = config.model

    def analyze_requirement(self, user_requirement: str) -> Dict[str, Any]:
        """分析用户需求，生成任务拆解"""
        # 预加载开发文档
        context = self.preload_context_files()

        # 返回分析结果（由实际 LLM 执行）
        return {
            "requirements_parsed": user_requirement,
            "context_loaded": bool(context),
            "needs_context_check": True,  # 是否需要 Kimi 做上下文检查
        }

    def design_architecture(self, requirement_analysis: Dict[str, Any]) -> List[AgentTask]:
        """根据需求分析，设计架构并拆解为子任务"""
        # 由 LLM 根据需求生成任务列表
        return []

    def review_results(self, all_results: List[AgentResult]) -> Tuple[bool, str]:
        """审核所有子 Agent 的执行结果，决定是否合并"""
        all_issues = []
        for result in all_results:
            if not result.success:
                all_issues.extend(result.issues_found)
            if result.issues_found:
                all_issues.extend(result.issues_found)

        if all_issues:
            return False, "\n".join(all_issues)
        return True, "所有任务执行通过，可以合并"

    def execute(self, task: AgentTask) -> AgentResult:
        """执行主任务（由 LLM 实际执行）"""
        # 这里是占位，实际执行由外部 LLM 调用层完成
        return AgentResult(
            task_id=task.task_id,
            success=True,
            message="Main agent task accepted",
            modified_files=[],
        )


class BackendAgent(AgentBase):
    """后端 Agent - DeepSeek

    职责：
    - 实现业务逻辑层 (business/)
    - 实现 ORM 服务层 (services/)
    - 实现数据模型层 (models/)
    - 实现数据库访问层 (db/)
    - 实现工具函数 (utils/)
    """

    def __init__(self, project_root: str = "."):
        config = WorkflowConfig.get_role_config(AgentRole.BACKEND)
        super().__init__(config, project_root)
        self.model = config.model

    def validate_architecture_compliance(self, file_path: str, code_content: str) -> List[str]:
        """检查代码是否符合开发基础文档的架构规范"""
        issues = []
        role_config = self.role_config

        # 检查是否在负责路径内
        if not self.is_path_allowed(file_path):
            issues.append(f"文件 {file_path} 不在后端 Agent 负责范围内")
            return issues

        # 检查命名规范（开发文档要求：小写+下划线）
        filename = Path(file_path).name
        if any(c.isupper() for c in filename) and not filename == "__init__.py":
            issues.append(f"文件名 {filename} 不符合规范：应使用小写+下划线")

        # 检查层级规范：业务层不能包含 Streamlit 代码
        if file_path.startswith("business/") and "st." in code_content:
            issues.append(f"业务层 {file_path} 不应包含 Streamlit UI 代码（st.xxx）")

        # 检查层级规范：禁止直接拼接 SQL 在 pages/business 层
        if file_path.startswith("business/") and "execute_query" in code_content:
            issues.append(f"业务层 {file_path} 不应直接调用数据库访问层 execute_query，应通过 services 层 ORM")

        # 检查数据类型：必须使用 dataclass 实体对象，禁止裸字典
        if file_path.startswith("models/") and "dataclass" not in code_content:
            issues.append(f"数据模型层 {file_path} 必须使用 @dataclass 定义实体类")

        return issues

    def execute(self, task: AgentTask) -> AgentResult:
        """执行后端开发任务"""
        # 检查所有路径是否允许
        for f in task.files:
            if not self.is_path_allowed(f):
                return AgentResult(
                    task_id=task.task_id,
                    success=False,
                    message=f"后端 Agent 无权限修改文件 {f}",
                    issues_found=[f"权限错误：{f} 不属于后端职责范围"],
                )

        # 预加载上下文
        context = self.preload_context_files()

        # 实际执行由外部 LLM 完成，这里只返回框架结果
        return AgentResult(
            task_id=task.task_id,
            success=True,
            message="后端任务分配完成，等待 LLM 执行",
            modified_files=task.files,
        )


class FrontendAgent(AgentBase):
    """前端 Agent - GLM

    职责：
    - 实现 Streamlit 页面 (pages/)
    - 实现可复用组件 (components/)
    - UI 交互与数据展示
    """

    def __init__(self, project_root: str = "."):
        config = WorkflowConfig.get_role_config(AgentRole.FRONTEND)
        super().__init__(config, project_root)
        self.model = config.model

    def validate_ui_compliance(self, file_path: str, code_content: str) -> List[str]:
        """检查前端代码是否符合架构规范"""
        issues = []

        if not self.is_path_allowed(file_path):
            issues.append(f"文件 {file_path} 不在前端 Agent 负责范围内")
            return issues

        # 检查命名规范
        filename = Path(file_path).name
        if any(c.isupper() for c in filename.split(".")[0]):
            issues.append(f"文件名 {filename} 不符合规范：应使用小写+下划线")

        # 检查页面层职责：禁止包含业务逻辑
        if file_path.startswith("pages/"):
            # 检查是否有太多业务逻辑
            lines = [line.strip() for line in code_content.splitlines()]
            business_logic_count = sum(
                1 for line in lines
                if "=" in line and "if " in line and not line.startswith("#")
                and "st." not in line
            )
            if business_logic_count > 10:
                issues.append(f"页面层 {file_path} 包含过多业务逻辑，应移入 business 层")

            # 检查是否直接操作数据库
            if "sqlite3" in code_content or "execute_" in code_content:
                issues.append(f"页面层 {file_path} 禁止直接操作数据库，必须通过 business 层")

        return issues

    def execute(self, task: AgentTask) -> AgentResult:
        """执行前端开发任务"""
        for f in task.files:
            if not self.is_path_allowed(f):
                return AgentResult(
                    task_id=task.task_id,
                    success=False,
                    message=f"前端 Agent 无权限修改文件 {f}",
                    issues_found=[f"权限错误：{f} 不属于前端职责范围"],
                )

        context = self.preload_context_files()

        return AgentResult(
            task_id=task.task_id,
            success=True,
            message="前端任务分配完成，等待 LLM 执行",
            modified_files=task.files,
        )


class TestAgent(AgentBase):
    """测试 & 复核 Agent - Qwen

    职责：
    - 代码审查 (Code Review)
    - 检查规范符合性
    - 执行测试验证
    - 最终复核
    """

    def __init__(self, project_root: str = "."):
        config = WorkflowConfig.get_role_config(AgentRole.TEST)
        super().__init__(config, project_root)
        self.model = config.model

    def code_review(self, file_path: str, code_content: str) -> List[str]:
        """代码审查，返回发现的问题列表"""
        issues = []

        # 1. 检查开发文档规范
        # 缩进是否为4个空格
        lines = code_content.splitlines()
        for i, line in enumerate(lines, 1):
            if line.startswith('\t'):
                issues.append(f"L{i}: 使用 Tab 缩进，应该使用4个空格")

        # 2. 检查命名规范
        # 类名应该大驼峰
        import re
        class_matches = re.findall(r'class\s+(\w+)', code_content)
        for cls_name in class_matches:
            if not cls_name[0].isupper():
                issues.append(f"类名 {cls_name} 不符合规范：应该使用大驼峰")

        # 函数/方法应该小写+下划线
        func_matches = re.findall(r'def\s+(\w+)', code_content)
        for func_name in func_matches:
            if func_name != "__init__" and any(c.isupper() for c in func_name):
                issues.append(f"函数/方法名 {func_name} 不符合规范：应该使用小写+下划线")

        # 3. 检查错误处理
        if "try:" in code_content and "except:" in code_content and "except Exception" not in code_content:
            issues.append("发现裸 except:，应该捕获具体异常类型")

        # 4. 检查硬编码
        if ("DB_PATH" not in code_content and "sqlite" in code_content and ".db" in code_content and
            "config" not in code_content):
            issues.append("发现硬编码数据库路径，应该从 config/settings.py 导入")

        return issues

    def run_static_check(self, modified_files: List[str]) -> List[str]:
        """对修改过的文件运行静态检查"""
        all_issues = []
        for rel_path in modified_files:
            abs_path = self.get_absolute_path(rel_path)
            if abs_path.exists() and abs_path.suffix == ".py":
                with open(abs_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    issues = self.code_review(rel_path, content)
                    all_issues.extend([f"{rel_path}: {issue}" for issue in issues])
        return all_issues

    def execute(self, task: AgentTask) -> AgentResult:
        """执行测试复核任务"""
        context = self.preload_context_files()

        # 对指定文件进行代码审查
        issues = self.run_static_check(task.files)

        success = len(issues) == 0

        return AgentResult(
            task_id=task.task_id,
            success=success,
            message=f"代码审查完成，发现 {len(issues)} 个问题" if issues else "代码审查通过，无问题",
            issues_found=issues,
            modified_files=[],  # 测试 Agent 不修改文件，只标记问题
        )


class ContextAgent(AgentBase):
    """超长上下文 Agent - Kimi

    职责：
    - 阅读全量项目文档确保一致性
    - 检查跨文件引用正确性
    - 提供全项目上下文摘要
    - 确保产出与开发文档一致
    """

    def __init__(self, project_root: str = "."):
        config = WorkflowConfig.get_role_config(AgentRole.CONTEXT)
        super().__init__(config, project_root)
        self.model = config.model

    def check_document_consistency(self) -> List[str]:
        """检查文档一致性，确保所有文档与当前代码结构一致"""
        issues = []
        dev_doc = self.get_absolute_path("docs/开发基础文档.md")

        if not dev_doc.exists():
            issues.append("找不到 docs/开发基础文档.md")
            return issues

        # 检查文档中提到的文件是否都存在
        # 这里只做基本检查，详细分析由 Kimi LLM 完成
        expected_dirs = [
            "config", "models", "db", "services", "business",
            "components", "utils", "pages", "scripts", "docs",
        ]
        for d in expected_dirs:
            dir_path = self.project_root / d
            if not dir_path.exists():
                issues.append(f"文档提到的目录 {d}/ 不存在")

        return issues

    def get_full_context_summary(self) -> str:
        """生成全项目上下文摘要，供其他 Agent 使用"""
        # 预加载所有文档
        all_context = self.preload_context_files()

        # 列出文件结构关键节点
        # 完整分析由 Kimi LLM 执行
        return f"""项目文件结构检查结果：
{len(all_context)} 个文档文件已加载，总计 {len(all_context)} 字符。

由 Kimi 基于超长上下文能力生成全项目一致性分析报告...
"""

    def execute(self, task: AgentTask) -> AgentResult:
        """执行上下文检查任务"""
        initial_issues = self.check_document_consistency()
        full_summary = self.get_full_context_summary()

        return AgentResult(
            task_id=task.task_id,
            success=len(initial_issues) == 0,
            message=f"上下文检查完成，发现 {len(initial_issues)} 个初始问题",
            issues_found=initial_issues,
            output_data={"full_context_summary": full_summary},
        )


def create_agent(role: AgentRole, project_root: str = ".") -> AgentBase:
    """工厂方法：根据角色创建对应的 Agent 实例"""
    agents_map = {
        AgentRole.MAIN: MainAgent,
        AgentRole.BACKEND: BackendAgent,
        AgentRole.FRONTEND: FrontendAgent,
        AgentRole.TEST: TestAgent,
        AgentRole.CONTEXT: ContextAgent,
    }
    agent_class = agents_map[role]
    return agent_class(project_root)