"""Agent 工作流系统 - 主入口

使用方法：
    python -m agent_workflow.main [命令]

命令：
    info       - 显示所有角色和模型分配信息
    demo       - 运行演示工作流
    workflow   - 显示可用的工作流模板
    run        - 运行指定类型的工作流
"""

import sys
from pathlib import Path

# 确保项目根在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_workflow.config import AgentRole, WorkflowConfig, RoleConfig
from agent_workflow.agents import (
    AgentBase, AgentTask, AgentResult,
    MainAgent, BackendAgent, FrontendAgent, TestAgent, ContextAgent,
    create_agent,
)
from agent_workflow.orchestrator import WorkflowOrchestrator
from agent_workflow.workflow import WorkflowType, WorkflowTask, WorkflowTemplates


def print_separator(title: str = ""):
    if title:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}\n")
    else:
        print(f"{'=' * 60}\n")


def cmd_info():
    """显示所有角色和模型分配信息"""
    print_separator("Agent 工作流系统 - 角色配置")

    print("系统架构：5 角色协作开发")
    print("┌──────────────────────────────────────────────────────────┐")
    print("│  主 Agent (DeepSeek)  ←── 对话沟通 & 架构协调           │")
    print("│     ├── 后端 Agent (DeepSeek)  ←── 业务逻辑 / ORM / DB │")
    print("│     ├── 前端 Agent (GLM)      ←── 页面 / 组件          │")
    print("│     ├── 测试 Agent (Qwen)     ←── 审查 / 测试 / 复核   │")
    print("│     └── 上下文 Agent (Kimi)   ←── 超长上下文 / 一致性  │")
    print("└──────────────────────────────────────────────────────────┘")

    print_separator("角色详细配置")

    roles_info = [
        (AgentRole.MAIN, "主 Agent", "对话沟通 · 架构设计 · 任务分发 · 审核合并", "DeepSeek"),
        (AgentRole.BACKEND, "后端 Agent", "业务逻辑层 · ORM服务层 · 数据模型层 · 数据库层 · 工具函数", "DeepSeek"),
        (AgentRole.FRONTEND, "前端 Agent", "Streamlit 页面 · 可复用组件 · UI 交互 · 数据展示", "GLM-4"),
        (AgentRole.TEST, "测试 & 复核 Agent", "代码审查 · 规范检查 · 测试验证 · 最终复核", "Qwen-Max"),
        (AgentRole.CONTEXT, "上下文 Agent", "全量文档阅读 · 一致性检查 · 跨文件引用验证 · 上下文摘要", "Kimi"),
    ]

    for role, name, desc, model in roles_info:
        config = WorkflowConfig.get_role_config(role)
        print(f"  [{model}] {name}")
        print(f"    职责: {desc}")
        print(f"    负责路径: {', '.join(config.responsible_paths) if config.responsible_paths else '全项目可读'}")
        if config.forbidden_paths:
            print(f"    禁止操作: {', '.join(config.forbidden_paths)}")
        print()


def cmd_workflow():
    """显示可用的工作流模板"""
    print_separator("可用的预定义工作流模板")

    workflow_info = [
        (WorkflowType.FEATURE_FULLSTACK, "全栈新功能", "前后端都涉及的新功能开发，完整流程"),
        (WorkflowType.FEATURE_BACKEND, "纯后端新功能", "只涉及后端（models/services/business）的新功能"),
        (WorkflowType.FEATURE_FRONTEND, "纯前端新功能", "只涉及前端（pages/components）的新功能"),
        (WorkflowType.BUG_FIX, "Bug 修复", "定位并修复 Bug"),
        (WorkflowType.REFACTOR, "代码重构", "代码重构，保持功能不变"),
        (WorkflowType.DOCS_UPDATE, "文档更新", "更新开发文档和用户手册"),
        (WorkflowType.CODE_REVIEW, "代码审查", "仅审查代码质量和规范，不修改"),
        (WorkflowType.ARCHITECTURE_CHANGE, "架构变更", "涉及架构层面的重大变更"),
    ]

    for wf_type, name, desc in workflow_info:
        template = WorkflowTemplates.get_template(wf_type)
        print(f"  [{wf_type.value}] {name}")
        print(f"    描述: {desc}")
        print(f"    阶段数: {len(template)}")
        for task in template:
            role_icon = {
                AgentRole.MAIN: "🎯",
                AgentRole.BACKEND: "🔧",
                AgentRole.FRONTEND: "🎨",
                AgentRole.TEST: "✅",
                AgentRole.CONTEXT: "📚",
            }.get(task.role, "•")
            dep = f" (依赖: {', '.join(task.depends_on)})" if task.depends_on else ""
            print(f"      {role_icon} {task.name} → {task.role.value}{dep}")
        print()


def cmd_demo():
    """运行演示工作流"""
    print_separator("Agent 工作流演示")

    # 1. 创建编排器
    orchestrator = WorkflowOrchestrator(project_root=".")

    # 2. 注册阶段完成回调
    def on_stage(stage):
        print(f"  [{stage.status}] {stage.name} - {stage.result.message if stage.result else '开始...'}")

    orchestrator.on_stage_complete(on_stage)

    # 3. 模拟一个全栈开发流程
    print("场景: 新增「试剂报废」功能\n")
    print("需求: 在试剂库存管理系统中新增试剂报废功能，")
    print("      包括报废原因记录、库存自动扣减、报废审批流程\n")

    # 模拟后端任务
    backend_task = AgentTask(
        task_id="TASK-001",
        description="实现试剂报废功能：新增报废数据模型、ORM服务、业务逻辑",
        files=[
            "models/core/scrap_record.py",
            "services/core/scrap_record_service.py",
            "business/scrap_service.py",
        ],
        context="新增试剂报废功能，需要：1) 新增 ScrapRecord 数据模型 2) 新增 scrap_record_service ORM 3) 新增 scrap_service 业务逻辑",
        role=AgentRole.BACKEND,
    )

    # 模拟前端任务
    frontend_task = AgentTask(
        task_id="TASK-002",
        description="实现试剂报废页面：报废表单、报废记录查询",
        files=[
            "pages/10_试剂报废.py",
        ],
        context="新增试剂报废页面，调用 business/scrap_service.py 的报废方法",
        role=AgentRole.FRONTEND,
    )

    # 4. 运行完整工作流
    result = orchestrator.run_full_workflow(
        requirement="新增试剂报废功能",
        backend_task=backend_task,
        frontend_task=frontend_task,
    )

    # 5. 打印报告
    print("\n")
    orchestrator.print_report()

    print(f"\n工作流状态: {result['status']}")
    print(f"总结: {result['summary']}")
    print(f"修改文件: {result['modified_files']}")


def cmd_run(workflow_type_str: str = "feature_fullstack"):
    """运行指定类型的工作流"""
    try:
        wf_type = WorkflowType(workflow_type_str)
    except ValueError:
        print(f"未知的工作流类型: {workflow_type_str}")
        print(f"可用类型: {[t.value for t in WorkflowType]}")
        return

    template = WorkflowTemplates.get_template(wf_type)
    print(f"运行工作流: {wf_type.value} ({len(template)} 个阶段)")

    orchestrator = WorkflowOrchestrator(project_root=".")

    def on_stage(stage):
        print(f"  [{stage.status}] {stage.name}")

    orchestrator.on_stage_complete(on_stage)

    # 按模板构建任务并执行
    for task_def in template:
        orchestrator.add_stage(
            name=task_def.name,
            role=task_def.role,
            description=task_def.description,
        )

    orchestrator.print_report()


def main():
    args = sys.argv[1:]

    if not args:
        print("Agent 工作流系统")
        print(f"用法: python -m agent_workflow.main <命令>")
        print(f"命令: info | demo | workflow | run [类型]")
        print(f"\n运行 'python -m agent_workflow.main info' 查看角色配置")
        print(f"运行 'python -m agent_workflow.main workflow' 查看可用工作流模板")
        return

    cmd = args[0].lower()

    commands = {
        "info": cmd_info,
        "demo": cmd_demo,
        "workflow": cmd_workflow,
        "run": lambda: cmd_run(args[1] if len(args) > 1 else "feature_fullstack"),
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"未知命令: {cmd}")
        print(f"可用命令: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()