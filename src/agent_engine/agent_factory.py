"""
Agent 工厂模块
统一管理不同类型 Agent 的创建
"""
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter

from src.config import DASHSCOPE_API_KEY, LLM_MODEL
from src.agent_engine.react_agent import create_react_agent


def create_research_agent(toolkit: Toolkit = None) -> ReActAgent:
    """创建研究助手 Agent。

    Args:
        toolkit: 工具箱

    Returns:
        研究助手 Agent
    """
    return create_react_agent(
        name="Research Agent",
        sys_prompt=(
            "你是一个专业的课程研究助理，专注于搜集和整理教学资料。\n"
            "请使用工具搜集相关资料，并整理为结构化的内容。"
        ),
        toolkit=toolkit,
    )


def create_review_agent(toolkit: Toolkit = None) -> ReActAgent:
    """创建质量审查 Agent。

    Args:
        toolkit: 工具箱

    Returns:
        质量审查 Agent
    """
    return create_react_agent(
        name="Review Agent",
        sys_prompt=(
            "你是一个严格的质量审查官，负责检查教学内容的质量。\n"
            "审查维度: 完整性、准确性、结构性、可读性。\n"
            "请给出每个维度的评分 (1-5分) 和具体的改进建议。"
        ),
        toolkit=toolkit,
    )


def create_planning_agent(toolkit: Toolkit = None) -> ReActAgent:
    """创建规划 Agent。

    Args:
        toolkit: 工具箱

    Returns:
        规划 Agent
    """
    return create_react_agent(
        name="Planning Agent",
        sys_prompt=(
            "你是一个善于规划和执行复杂任务的助理。\n"
            "收到任务后，先生成详细的执行计划，然后逐步完成每个子任务。"
        ),
        toolkit=toolkit,
    )
