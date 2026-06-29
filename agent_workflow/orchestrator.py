"""工作流编排器 - 协调多个 Agent 协作完成任务

编排器负责：
1. 接收用户需求，通过主 Agent 分析拆解
2. 将子任务分发给对应的 Agent
3. 收集结果，交由测试 Agent 审查
4. 最终由主 Agent 审核合并
"""

import logging
from typing import List, Dict, Any, Optional, Callable, Tuple
from datetime import datetime
from pathlib import Path

from .config import AgentRole, WorkflowConfig
from .agents import (
    AgentBase, AgentTask, AgentResult,
    MainAgent, BackendAgent, FrontendAgent, TestAgent, ContextAgent,
    create_agent,
)

logger = logging.getLogger(__name__)


class WorkflowStage:
    """单个工作流阶段"""

    def __init__(self, name: str, role: AgentRole, description: str):
        self.name = name
        self.role = role
        self.description = description
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.result: Optional[AgentResult] = None
        self.status: str = "pending"  # pending | running | success | failed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "description": self.description,
            "status": self.status,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "success": self.result.success if self.result else None,
            "message": self.result.message if self.result else None,
            "issues": self.result.issues_found if self.result else [],
        }


class WorkflowOrchestrator:
    """工作流编排器

    协调 5 个角色的 Agent 按照开发流程协作完成任务。

    典型流程：
    1. 需求分析 → 主 Agent (DeepSeek)
    2. 上下文检查 → 上下文 Agent (Kimi)
    3. 后端开发 → 后端 Agent (DeepSeek)
    4. 前端开发 → 前端 Agent (GLM)
    5. 代码审查 → 测试 Agent (Qwen)
    6. 上下文复核 → 上下文 Agent (Kimi)
    7. 合并提交 → 主 Agent (DeepSeek)
    """

    def __init__(self, project_root: str = "."):
        self.project_root = project_root
        self._init_agents()
        self.stages: List[WorkflowStage] = []
        self.completed_stages: List[WorkflowStage] = []
        self.all_results: List[AgentResult] = []
        self._stage_index = 0
        self._callbacks: List[Callable[[WorkflowStage], None]] = []

    def _init_agents(self):
        """初始化所有 Agent 实例"""
        self.agents: Dict[AgentRole, AgentBase] = {
            AgentRole.MAIN: create_agent(AgentRole.MAIN, self.project_root),
            AgentRole.BACKEND: create_agent(AgentRole.BACKEND, self.project_root),
            AgentRole.FRONTEND: create_agent(AgentRole.FRONTEND, self.project_root),
            AgentRole.TEST: create_agent(AgentRole.TEST, self.project_root),
            AgentRole.CONTEXT: create_agent(AgentRole.CONTEXT, self.project_root),
        }

    def get_agent(self, role: AgentRole) -> AgentBase:
        """获取指定角色的 Agent"""
        return self.agents[role]

    def get_main_agent(self) -> MainAgent:
        """获取主 Agent"""
        return self.agents[AgentRole.MAIN]

    def get_backend_agent(self) -> BackendAgent:
        """获取后端 Agent"""
        return self.agents[AgentRole.BACKEND]

    def get_frontend_agent(self) -> FrontendAgent:
        """获取前端 Agent"""
        return self.agents[AgentRole.FRONTEND]

    def get_test_agent(self) -> TestAgent:
        """获取测试 Agent"""
        return self.agents[AgentRole.TEST]

    def get_context_agent(self) -> ContextAgent:
        """获取上下文 Agent"""
        return self.agents[AgentRole.CONTEXT]

    def on_stage_complete(self, callback: Callable[[WorkflowStage], None]):
        """注册阶段完成回调"""
        self._callbacks.append(callback)

    def _emit_stage_event(self, stage: WorkflowStage):
        """触发阶段事件"""
        for callback in self._callbacks:
            try:
                callback(stage)
            except Exception as e:
                logger.error(f"回调执行失败: {e}")

    def add_stage(self, name: str, role: AgentRole, description: str) -> "WorkflowOrchestrator":
        """添加一个工作流阶段（链式调用）"""
        stage = WorkflowStage(name, role, description)
        self.stages.append(stage)
        return self

    def execute_stage(self, stage: WorkflowStage, task: AgentTask) -> AgentResult:
        """执行单个工作流阶段"""
        stage.status = "running"
        stage.start_time = datetime.now()
        self._emit_stage_event(stage)

        try:
            agent = self.agents[stage.role]
            result = agent.execute(task)
            stage.result = result
            stage.status = "success" if result.success else "failed"
        except Exception as e:
            stage.result = AgentResult(
                task_id=task.task_id,
                success=False,
                message=str(e),
                issues_found=[f"执行异常: {e}"],
            )
            stage.status = "failed"

        stage.end_time = datetime.now()
        self.completed_stages.append(stage)
        self._emit_stage_event(stage)
        return stage.result

    def run_full_workflow(
        self,
        requirement: str,
        frontend_task: Optional[AgentTask] = None,
        backend_task: Optional[AgentTask] = None,
    ) -> Dict[str, Any]:
        """运行完整的开发工作流

        标准流程：
        1. 需求分析 (Main)
        2. 上下文检查 (Context)
        3. 后端开发 (Backend)
        4. 前端开发 (Frontend)
        5. 代码审查 (Test)
        6. 上下文复核 (Context)
        7. 审核合并 (Main)

        Args:
            requirement: 用户需求描述
            frontend_task: 前端开发任务（可选，由主 Agent 自动生成）
            backend_task: 后端开发任务（可选，由主 Agent 自动生成）

        Returns:
            工作流执行结果汇总
        """
        task_counter = 0
        all_results = []

        # 阶段 1: 需求分析 (Main Agent - DeepSeek)
        task_counter += 1
        main_agent = self.get_main_agent()
        analysis = main_agent.analyze_requirement(requirement)

        stage1 = WorkflowStage("需求分析", AgentRole.MAIN, "主 Agent 分析需求，查阅开发文档")
        result1 = self.execute_stage(stage1, AgentTask(
            task_id=f"TASK-{task_counter:03d}",
            description=f"分析需求: {requirement}",
            files=["docs/开发基础文档.md"],
            context=requirement,
            role=AgentRole.MAIN,
            metadata={"analysis": analysis},
        ))
        all_results.append(result1)

        if result1.pending_confirmation:
            return {
                "status": "pending_confirmation",
                "question": result1.confirmation_question,
                "stages": [s.to_dict() for s in self.completed_stages],
            }

        # 阶段 2: 上下文检查 (Context Agent - Kimi)
        task_counter += 1
        stage2 = WorkflowStage("上下文检查", AgentRole.CONTEXT, "Kimi 检查全量文档一致性")
        result2 = self.execute_stage(stage2, AgentTask(
            task_id=f"TASK-{task_counter:03d}",
            description="检查全项目文档一致性，确保与开发基础文档吻合",
            files=["docs/"],
            context=requirement,
            role=AgentRole.CONTEXT,
        ))
        all_results.append(result2)

        # 如果有上下文问题，先报告
        if result2.issues_found:
            logger.warning(f"上下文检查发现问题: {result2.issues_found}")

        # 阶段 3: 后端开发 (Backend Agent - DeepSeek)
        if backend_task:
            task_counter += 1
            stage3 = WorkflowStage("后端开发", AgentRole.BACKEND, "DeepSeek 实现后端业务逻辑")
            backend_task.task_id = f"TASK-{task_counter:03d}"
            result3 = self.execute_stage(stage3, backend_task)
            all_results.append(result3)

        # 阶段 4: 前端开发 (Frontend Agent - GLM)
        if frontend_task:
            task_counter += 1
            stage4 = WorkflowStage("前端开发", AgentRole.FRONTEND, "GLM 实现前端页面")
            frontend_task.task_id = f"TASK-{task_counter:03d}"
            result4 = self.execute_stage(stage4, frontend_task)
            all_results.append(result4)

        # 收集所有修改的文件用于审查
        all_modified_files = []
        for r in all_results:
            all_modified_files.extend(r.modified_files)

        # 阶段 5: 代码审查 (Test Agent - Qwen)
        if all_modified_files:
            task_counter += 1
            stage5 = WorkflowStage("代码审查", AgentRole.TEST, "Qwen 审查代码质量与规范")
            result5 = self.execute_stage(stage5, AgentTask(
                task_id=f"TASK-{task_counter:03d}",
                description="对所有修改文件进行代码审查",
                files=all_modified_files,
                context=requirement,
                role=AgentRole.TEST,
            ))
            all_results.append(result5)

        # 阶段 6: 上下文复核 (Context Agent - Kimi)
        task_counter += 1
        stage6 = WorkflowStage("上下文复核", AgentRole.CONTEXT, "Kimi 最终一致性检查")
        result6 = self.execute_stage(stage6, AgentTask(
            task_id=f"TASK-{task_counter:03d}",
            description="最终检查修改后的代码与文档一致性",
            files=["docs/"],
            context=requirement,
            role=AgentRole.CONTEXT,
        ))
        all_results.append(result6)

        # 阶段 7: 审核合并 (Main Agent - DeepSeek)
        task_counter += 1
        stage7 = WorkflowStage("审核合并", AgentRole.MAIN, "主 Agent 审核所有结果，决定是否合并")
        passed, review_msg = main_agent.review_results(all_results)
        result7 = self.execute_stage(stage7, AgentTask(
            task_id=f"TASK-{task_counter:03d}",
            description="审核所有子 Agent 结果，决定合并或退回",
            files=all_modified_files,
            context=review_msg,
            role=AgentRole.MAIN,
            metadata={"all_results": all_results},
        ))
        all_results.append(result7)

        return {
            "status": "completed",
            "summary": review_msg,
            "all_passed": passed,
            "stages": [s.to_dict() for s in self.completed_stages],
            "total_tasks": task_counter,
            "modified_files": all_modified_files,
        }

    def get_status_report(self) -> str:
        """生成工作流状态报告"""
        lines = ["=" * 60, "Agent 工作流执行状态报告", "=" * 60, ""]

        for stage in self.completed_stages:
            status_icon = "✓" if stage.result and stage.result.success else "✗"
            lines.append(f"  [{stage.status}] {status_icon} {stage.name}")
            lines.append(f"        角色: {stage.role.value} ({WorkflowConfig.get_role_config(stage.role).model})")
            lines.append(f"        描述: {stage.description}")
            if stage.result:
                lines.append(f"        结果: {stage.result.message}")
                if stage.result.issues_found:
                    for issue in stage.result.issues_found:
                        lines.append(f"          - {issue}")
            if stage.start_time and stage.end_time:
                duration = (stage.end_time - stage.start_time).total_seconds()
                lines.append(f"        耗时: {duration:.2f}s")
            lines.append("")

        # 待执行阶段
        pending = [s for s in self.stages if s.status == "pending"]
        if pending:
            lines.append("  待执行阶段:")
            for s in pending:
                lines.append(f"    - {s.name} ({s.role.value})")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def print_report(self):
        """打印工作流状态报告"""
        print(self.get_status_report())