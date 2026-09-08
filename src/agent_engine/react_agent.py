"""
ReAct Agent 模块
实现思考-行动-观察循环
"""
import os
import asyncio
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory

from src.config import DASHSCOPE_API_KEY, LLM_MODEL, MAX_REACT_ITERS, TEMPERATURE


def create_react_agent(
    name: str = "Teaching Assistant",
    sys_prompt: str = "你是一个智能教学助手，擅长使用工具搜集和整理教学资料。",
    toolkit: Toolkit = None,
    max_iters: int = None,
) -> ReActAgent:
    """创建 ReAct Agent。

    Args:
        name: Agent 名称
        sys_prompt: 系统提示词
        toolkit: 工具箱，默认创建空工具箱
        max_iters: 最大 ReAct 循环次数

    Returns:
        ReActAgent 实例
    """
    if toolkit is None:
        toolkit = Toolkit()

    agent = ReActAgent(
        name=name,
        sys_prompt=sys_prompt,
        model=DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        ),
        toolkit=toolkit,
        formatter=DashScopeChatFormatter(),
        memory=InMemoryMemory(),
        max_iters=max_iters or MAX_REACT_ITERS,
    )

    return agent


async def run_agent_query(
    question: str,
    agent: ReActAgent = None,
    toolkit: Toolkit = None,
) -> str:
    """运行 Agent 问答。

    Args:
        question: 用户问题
        agent: 已有 Agent 实例，或 None 创建新实例
        toolkit: 工具箱

    Returns:
        Agent 回复内容
    """
    if agent is None:
        agent = create_react_agent(toolkit=toolkit)

    from agentscope.message import Msg

    msg = Msg(name="user", content=question, role="user")
    response = await agent(msg)

    return response.content
