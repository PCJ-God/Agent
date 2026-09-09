"""
PlanNotebook 自主规划模块
实现 Agent 自主创建计划、逐步执行、灵活调整的能力

工具来源: MCP 工具 (通过 register_mcp_tools 注册)
"""
import asyncio
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.message import Msg
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter
from agentscope.plan import PlanNotebook

from src.config import DASHSCOPE_API_KEY, LLM_MODEL
from src.tools.tool_manager import register_mcp_tools, close_mcp_client


# 用于监控计划变化的钩子函数
plan_snapshots = []


def capture_plan_snapshot(notebook, plan):
    """捕获计划快照。

    Args:
        notebook: PlanNotebook 实例
        plan: 当前计划
    """
    if plan:
        plan_snapshots.append({
            "name": plan.name,
            "description": plan.description,
            "state": plan.state,
            "subtasks": [
                {
                    "name": st.name,
                    "state": st.state,
                    "outcome": st.outcome
                }
                for st in plan.subtasks
            ]
        })


async def run_planning_workflow(user_request: str, toolkit: Toolkit , mcp_client=None) -> str:
    """运行自主规划演示。

    Args:
        user_request: 用户请求
        toolkit: 共享工具箱 (None 时创建)
        mcp_client: MCP 客户端 (None 时自行注册)

    Returns:
        Agent 的回复文本
    """
    global plan_snapshots
    plan_snapshots = []

    # 创建 PlanNotebook 并注册钩子
    plan_notebook = PlanNotebook()
    plan_notebook.register_plan_change_hook("capture", capture_plan_snapshot)

    # 使用共享工具箱或创建新的
    own_client = False
    if toolkit is None:
        toolkit = Toolkit()
        mcp_client = await register_mcp_tools(toolkit)
        own_client = True

    try:
        # 创建 Agent
        agent = ReActAgent(
            name="CourseResearcherAgent",
            sys_prompt=(
                "你是课程调研助手。遇到复杂任务时:\n"
                "1. 用 create_plan 创建计划\n"
                "2. 逐步执行，用 finish_subtask 标记完成\n"
                "3. 遇到问题灵活调整，使用可用工具寻找替代方案\n"
                "4. 完成后用 finish_plan 结束"
            ),
            model=DashScopeChatModel(
                model_name=LLM_MODEL,
                api_key=DASHSCOPE_API_KEY,
            ),
            formatter=DashScopeChatFormatter(),
            toolkit=toolkit,
            plan_notebook=plan_notebook,
        )

        # 用户请求
        msg = Msg("user", user_request, "user")
        response = await agent(msg)

        # 提取回复文本
        if hasattr(response, 'content'):
            content = response.content
            if isinstance(content, list):
                texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("text")]
                return "\n".join(texts) if texts else str(content)
            return str(content)
        return str(response)

    finally:
        if own_client and mcp_client:
            await close_mcp_client(mcp_client)
