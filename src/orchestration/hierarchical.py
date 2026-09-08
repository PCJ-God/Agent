"""
层级协作模式 (Hierarchical)
Leader Agent 通过 Handoff 分发给 Member Agents
"""
import asyncio
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit, ToolResponse
from agentscope.message import Msg, TextBlock

from src.agent_engine.agent_factory import (
    create_research_agent,
    create_review_agent,
)


class HierarchicalTeam:
    """层级协作团队，保持 Agent 状态跨多轮对话。"""

    def __init__(self):
        # 创建 Member Agents (持久化实例，保留对话历史)
        self.researcher = create_research_agent()
        self.reviewer = create_review_agent()

        # 创建 Leader，将 Members 注册为工具 (Handoff 机制)
        toolkit = Toolkit()

        def invoke_researcher(requirement: str) -> ToolResponse:
            """调用研究助手搜集资料。

            Args:
                requirement: 搜集需求描述
            """
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    self.researcher(Msg(name="leader", content=requirement, role="user"))
                )
                return ToolResponse(content=[TextBlock(type="text", text=result.content)])
            finally:
                loop.close()

        def invoke_reviewer(content: str) -> ToolResponse:
            """调用审查 Agent 检查质量。

            Args:
                content: 待审查的内容
            """
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    self.reviewer(Msg(name="leader", content=f"请审查:\n{content}", role="user"))
                )
                return ToolResponse(content=[TextBlock(type="text", text=result.content)])
            finally:
                loop.close()

        toolkit.register_tool_function(invoke_researcher)
        toolkit.register_tool_function(invoke_reviewer)

        from src.agent_engine.react_agent import create_react_agent

        self.leader = create_react_agent(
            name="Project Leader",
            sys_prompt=(
                "你是一个项目负责人，负责协调和分配任务。\n"
                "你有两个团队成员可以使用:\n"
                "- invoke_researcher: 研究助手，负责搜集资料\n"
                "- invoke_reviewer: 审查专家，负责质量审查\n"
                "请根据任务需求，依次调用团队成员完成工作。"
            ),
            toolkit=toolkit,
        )

    async def chat(self, user_request: str) -> str:
        """发送消息并获取回复 (保留上下文)。

        Args:
            user_request: 用户请求

        Returns:
            Leader 的回复内容
        """
        msg = Msg(name="user", content=user_request, role="user")
        response = await self.leader(msg)
        return response.content


async def run_hierarchical(user_request: str) -> str:
    """运行层级协作模式 (单次调用，向后兼容)。

    Args:
        user_request: 用户请求

    Returns:
        Leader Agent 的最终回复
    """
    team = HierarchicalTeam()
    return await team.chat(user_request)
