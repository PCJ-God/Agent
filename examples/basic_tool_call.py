"""
基础工具调用示例
演示 Function Calling 的完整流程
"""

import asyncio
import os
import json
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit, ToolResponse
from agentscope.model import DashScopeChatModel
from agentscope.message import Msg, TextBlock
from agentscope.formatter import DashScopeChatFormatter


def web_search(query: str, max_results: int = 3) -> ToolResponse:
    """模拟联网搜索工具。
    
    Args:
        query (str): 搜索关键词
        max_results (int): 最大返回结果数量,默认3
    """
    print(f"\n--- [工具执行] 正在搜索: {query} ---")
    
    # 模拟搜索结果
    mock_results = {
        "Transformer": [
            {"title": "Attention Is All You Need", "url": "https://arxiv.org/abs/1706.03762"},
            {"title": "Transformer架构详解", "url": "https://example.com/transformer"},
        ],
        "BERT": [
            {"title": "BERT: Pre-training of Deep Bidirectional Transformers", "url": "https://arxiv.org/abs/1810.04805"},
        ],
    }
    
    results = mock_results.get(query, [{"title": f"关于'{query}'的搜索结果", "url": "https://example.com"}])
    result_text = "\n".join([f"{i+1}. {r['title']} - {r['url']}" for i, r in enumerate(results[:max_results])])
    
    return ToolResponse(
        content=[TextBlock(type="text", text=f"搜索结果:\n{result_text}")]
    )


def search_arxiv_paper(query: str) -> ToolResponse:
    """模拟学术论文搜索工具。
    
    Args:
        query (str): 论文标题或关键词
    """
    print(f"\n--- [工具执行] 正在Arxiv搜索: {query} ---")
    
    # 模拟论文搜索结果
    mock_papers = {
        "Attention Is All You Need": {
            "title": "Attention Is All You Need",
            "authors": "Vaswani et al.",
            "year": "2017",
            "url": "https://arxiv.org/abs/1706.03762"
        },
        "BERT": {
            "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
            "authors": "Devlin et al.",
            "year": "2018",
            "url": "https://arxiv.org/abs/1810.04805"
        },
    }
    
    paper = mock_papers.get(query, {"title": query, "authors": "Unknown", "year": "N/A", "url": "N/A"})
    result_text = f"找到论文: {paper['title']}\n作者: {paper['authors']}\n年份: {paper['year']}\n链接: {paper['url']}"
    
    return ToolResponse(
        content=[TextBlock(type="text", text=result_text)]
    )


async def run_basic_tool_call():
    """运行基础工具调用示例"""
    
    # 1. 创建工具箱并注册工具函数
    toolkit = Toolkit()
    toolkit.register_tool_function(web_search)
    toolkit.register_tool_function(search_arxiv_paper)
    
    # 2. 创建 ReActAgent
    agent = ReActAgent(
        name="Research Assistant",
        sys_prompt="""你是一个课程研究助理,擅长使用工具搜集和整理教学资料。
        
你的工作流程:
1. 理解用户需求
2. 使用合适的工具搜集资料 (web_search 用于通用搜索, search_arxiv_paper 用于学术论文)
3. 整理和汇总搜集到的信息
4. 生成结构化的教学建议""",
        model=DashScopeChatModel(
            model_name="qwen-plus",
            api_key=os.environ.get("DASHSCOPE_API_KEY")
        ),
        toolkit=toolkit,
        formatter=DashScopeChatFormatter()
    )
    
    # 3. 发送用户请求
    user_requests = [
        "帮我搜集一些关于 Transformer 模型的教学资料",
        "找到 'Attention Is All You Need' 这篇论文",
        "搜集 BERT 模型的最新研究进展"
    ]
    
    for request in user_requests:
        print(f"\n{'='*60}")
        print(f"用户请求: {request}")
        print(f"{'='*60}")
        
        msg = Msg(name="user", content=request, role="user")
        response = await agent(msg)
        
        print(f"\nAgent 回复:\n{response.content}")
        print(f"\n{'='*60}\n")


if __name__ == "__main__":
    # 确保已设置环境变量
    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("错误: 请设置 DASHSCOPE_API_KEY 环境变量")
        exit(1)
    
    asyncio.run(run_basic_tool_call())
