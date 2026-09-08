"""
工具管理模块
负责工具注册、调用和管理
"""
from agentscope.tool import Toolkit, ToolResponse
from agentscope.message import TextBlock


def register_default_tools(toolkit: Toolkit) -> Toolkit:
    """注册默认工具集。

    AgentScope 会自动从工具的 docstring 解析 JSON Schema。

    Args:
        toolkit: 工具箱实例

    Returns:
        已注册工具的 toolkit
    """
    toolkit.register_tool_function(web_search)
    toolkit.register_tool_function(search_arxiv_paper)

    return toolkit


def web_search(query: str, max_results: int = 3) -> ToolResponse:
    """联网搜索最新资料。

    Args:
        query: 搜索关键词
        max_results: 最大返回结果数量，默认3
    """
    # 实际环境中这里会调用真实的搜索引擎 API
    print(f"  [web_search] 正在搜索: {query}")
    return ToolResponse(
        content=[TextBlock(
            type="text",
            text=f"已搜索 '{query}'，找到 {max_results} 条相关资料。"
        )]
    )


def search_arxiv_paper(query: str) -> ToolResponse:
    """在 Arxiv.org 搜索学术论文。

    Args:
        query: 论文标题或关键词
    """
    print(f"  [search_arxiv_paper] 正在搜索: {query}")
    return ToolResponse(
        content=[TextBlock(
            type="text",
            text=f"已搜索到关于 '{query}' 的相关论文。"
        )]
    )
