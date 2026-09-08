"""
MCP 集成示例
演示如何集成本地 MCP Server 和远程 MCP 服务
"""

import asyncio
import os
import sys
from agentscope.agent import ReActAgent
from agentscope.mcp import StdIOStatefulClient, HttpStatelessClient
from agentscope.tool import Toolkit
from agentscope.model import DashScopeChatModel
from agentscope.message import Msg
from agentscope.formatter import DashScopeChatFormatter


async def run_local_mcp_example():
    """运行本地 MCP Server 示例 (stdio 模式)"""
    print("\n=== 本地 MCP Server 示例 (stdio 模式) ===\n")
    
    # 1. 创建 MCP Client,指向本地 MCP Server
    #    这里通过 stdio 方式启动同目录下的 MCP Server 脚本
    web_search_client = StdIOStatefulClient(
        name="web_search_service",
        command=sys.executable,
        args=["mcp_servers/web_search_server.py"],
        cwd=os.getcwd()
    )
    
    # 2. 连接 MCP Server
    await web_search_client.connect()
    print("已连接到本地 MCP Server")
    
    # 3. 将 MCP Client 的工具注册到 Toolkit
    toolkit = Toolkit()
    await toolkit.register_mcp_client(web_search_client)
    print("MCP 工具已注册到 Toolkit")
    
    # 4. 创建 ReActAgent
    agent = ReActAgent(
        name="MCP Research Assistant",
        sys_prompt="你是一个课程研究助理,使用MCP工具搜集教学资料。",
        model=DashScopeChatModel(
            model_name="qwen-plus",
            api_key=os.environ.get("DASHSCOPE_API_KEY")
        ),
        toolkit=toolkit,
        formatter=DashScopeChatFormatter()
    )
    
    # 5. 发送请求
    user_request = "我正在为'大模型原理'课程搜集素材,请帮我搜索一下最近关于'大型语言模型'的最新进展。"
    print(f"\n用户请求: {user_request}\n")
    
    msg = Msg(name="user", content=user_request, role="user")
    response = await agent(msg)
    
    print(f"\nAgent 回复:\n{response.content}")
    
    # 6. 关闭 MCP Client
    await web_search_client.close()
    print("\n已关闭 MCP Client")


async def run_remote_mcp_example():
    """运行远程 MCP 服务示例 (Streamable HTTP 模式)"""
    print("\n=== 远程 MCP 服务示例 (Streamable HTTP 模式) ===\n")
    print("注意: 此示例需要阿里云百炼平台的 API Key")
    print("请前往 https://bailian.console.aliyun.com 开通联网搜索 MCP 服务\n")
    
    # 1. 创建 HTTP MCP Client,指向阿里云百炼的 WebSearch MCP 服务
    web_search_client = HttpStatelessClient(
        name="web_search_service",
        transport="streamable_http",
        url="https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp",
        headers={"Authorization": "Bearer " + os.environ.get("DASHSCOPE_API_KEY")}
    )
    
    # 2. 将 MCP Client 的工具注册到 Toolkit
    toolkit = Toolkit()
    await toolkit.register_mcp_client(web_search_client)
    print("远程 MCP 工具已注册到 Toolkit")
    
    # 3. 创建 ReActAgent
    agent = ReActAgent(
        name="Cloud MCP Research Assistant",
        sys_prompt="你是一个课程研究助理,使用云端MCP工具搜集最新教学素材。",
        model=DashScopeChatModel(
            model_name="qwen-plus",
            api_key=os.environ.get("DASHSCOPE_API_KEY")
        ),
        toolkit=toolkit,
        formatter=DashScopeChatFormatter()
    )
    
    # 4. 发送请求
    user_request = "我正在为'大模型原理'课程搜集素材,请帮我搜索一下最近关于'大型语言模型'的最新进展。"
    print(f"\n用户请求: {user_request}\n")
    
    msg = Msg(name="user", content=user_request, role="user")
    response = await agent(msg)
    
    print(f"\nAgent 回复:\n{response.content}")


async def main():
    """主函数"""
    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("错误: 请设置 DASHSCOPE_API_KEY 环境变量")
        exit(1)
    
    # 运行本地 MCP 示例
    await run_local_mcp_example()
    
    # 运行远程 MCP 示例 (可选)
    # await run_remote_mcp_example()


if __name__ == "__main__":
    asyncio.run(main())
