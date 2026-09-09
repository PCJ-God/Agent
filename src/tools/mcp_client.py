"""
MCP 客户端模块
支持 stdio 和 Streamable HTTP 两种传输模式
"""
import os
import sys
import asyncio
from agentscope.mcp import StdIOStatefulClient, HttpStatelessClient
from agentscope.tool import Toolkit

from src.config import (
    DASHSCOPE_API_KEY,
    MCP_TRANSPORT,
    MCP_SERVER_URL,
    MCP_SERVERS_DIR,
)


async def create_mcp_client(
    name: str = "web_search_service",
    transport: str = "",
) -> StdIOStatefulClient | HttpStatelessClient:
    """创建 MCP 客户端。

    Args:
        name: 客户端名称
        transport: 传输模式 (stdio / streamable_http)

    Returns:
        MCP 客户端实例
    """
    transport = transport or MCP_TRANSPORT

    if transport == "stdio":
        client = StdIOStatefulClient(
            name=name,
            command=sys.executable,
            args=[str(MCP_SERVERS_DIR / "web_search_server.py")],
            cwd=os.getcwd(),
        )
        await client.connect()
        return client

    elif transport == "streamable_http":
        client = HttpStatelessClient(
            name=name,
            transport="streamable_http",
            url=MCP_SERVER_URL,
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
        )
        return client

    else:
        raise ValueError(f"不支持的 MCP 传输模式: {transport}")


async def register_mcp_tools(toolkit: Toolkit, client) -> None:
    """将 MCP Server 的工具注册到 Toolkit。

    Args:
        toolkit: 工具箱实例
        client: MCP 客户端实例
    """
    await toolkit.register_mcp_client(client)


async def close_mcp_client(client) -> None:
    """关闭 MCP 客户端连接。

    Args:
        client: MCP 客户端实例
    """
    if isinstance(client, StdIOStatefulClient):
        await client.close()
