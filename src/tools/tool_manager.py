"""
工具管理模块
负责工具注册、调用和管理

工具来源:
1. MCP 工具 (连接远端 MCP Server)
2. Skill (SKILL.md 定义的标准化流程)
3. 动态工具注册 (Agent 运行时通过代码解释器创建)
"""
import asyncio
import os
import sys
from agentscope.tool import Toolkit
from agentscope.mcp import StdIOStatefulClient, HttpStatelessClient

from src.config import (
    DASHSCOPE_API_KEY,
    MCP_TRANSPORT,
    MCP_SERVER_URL,
    MCP_SERVERS_DIR,
)


async def register_mcp_tools(toolkit: Toolkit, transport: str = "") -> StdIOStatefulClient | HttpStatelessClient:
    """注册 MCP 工具到 Toolkit。

    Args:
        toolkit: 工具箱实例
        transport: 传输模式 (stdio / streamable_http)

    Returns:
        MCP 客户端实例
    """
    transport = transport or MCP_TRANSPORT

    if transport == "stdio":
        server_script = MCP_SERVERS_DIR / "web_search_server.py"
        client = StdIOStatefulClient(
            name="web_search_service",
            command=sys.executable,
            args=[str(server_script)],
            cwd=os.getcwd(),
        )
        await client.connect()

    elif transport == "streamable_http":
        client = HttpStatelessClient(
            name="web_search_service",
            transport="streamable_http",
            url=MCP_SERVER_URL,
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
        )

    else:
        raise ValueError(f"不支持的 MCP 传输模式: {transport}")

    await toolkit.register_mcp_client(client)
    return client


def register_skill_tools(toolkit: Toolkit, skills_dir: str = "") -> list:
    """注册 Skill 定义的工具。

    AgentScope 的 register_agent_skill 会从 SKILL.md 的 frontmatter
    中提取 name 和 description，注入到系统提示中 (渐进式披露)。

    Args:
        toolkit: 工具箱实例
        skills_dir: Skill 目录路径

    Returns:
        已注册的 Skill 名称列表
    """
    from src.skills.skill_loader import SkillManager

    manager = SkillManager(skills_dir)
    registered = []

    for skill_info in manager.list_skills():
        skill_path = manager.skills_dir / skill_info["name"] / "SKILL.md"
        if skill_path.exists():
            toolkit.register_agent_skill(str(skill_path.parent))
            registered.append(skill_info["name"])

    return registered


async def close_mcp_client(client) -> None:
    """关闭 MCP 客户端连接。

    Args:
        client: MCP 客户端实例
    """
    if isinstance(client, StdIOStatefulClient):
        await client.close()
