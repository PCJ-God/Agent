"""
动态工具创建模块
实现 Agent 在规划过程中自主创建新工具的能力

Agent 通过代码解释器 (execute_python_code) 自主创建和注册新工具
"""
import asyncio
import sys
from io import StringIO

from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit, ToolResponse, execute_python_code
from agentscope.message import Msg, TextBlock
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter

from src.config import DASHSCOPE_API_KEY, LLM_MODEL


# 全局工具箱 (供 Agent 创建的工具注册使用)
_global_toolkit = None


async def run_dynamic_tool_creation() -> dict:
    """运行动态工具创建演示。

    Agent 使用 execute_python_code 工具自主创建新工具。

    Returns:
        执行结果字典
    """
    global _global_toolkit
    _global_toolkit = Toolkit()

    # 注册代码解释器工具 (AgentScope 内置)
    _global_toolkit.register_tool_function(execute_python_code)

    agent = ReActAgent(
        name="ToolMaker",
        sys_prompt=(
            "你可以通过 execute_python_code 创建新工具。\n"
            "模板:\n"
            "async def tool_name(param: type) -> ToolResponse:\n"
            "    '''描述'''\n"
            "    result = ...\n"
            "    return ToolResponse(content=[TextBlock(type='text', text=f'{result}')])\n"
            "agent_toolkit.register_tool_function(tool_name)\n"
            "print('✅ 已注册 tool_name')"
        ),
        model=DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        ),
        formatter=DashScopeChatFormatter(),
        toolkit=_global_toolkit,
    )

    # 场景 1: Agent 自主创建加法工具
    await agent(Msg("user", "创建一个 add 工具，计算两个数的和", "user"))

    # 场景 2: Agent 创建阶乘工具
    await agent(Msg("user", "创建 factorial 工具计算阶乘", "user"))

    # 场景 3: Agent 使用新创建的工具
    response = await agent(Msg("user", "用 factorial 计算 5 的阶乘", "user"))

    # 显示工具箱
    tools = [s['function']['name'] for s in _global_toolkit.get_json_schemas()]

    return {
        "initial_tools": ["execute_python_code"],
        "final_tools": tools,
        "new_tools_created": [t for t in tools if t != "execute_python_code"],
        "last_response": response.content if response else "",
    }
