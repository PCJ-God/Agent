"""
WebSearch MCP Server
本地模拟联网搜索服务，用于开发调试
"""
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# 创建本地 MCP Server 实例
mcp = FastMCP("MockWebSearch")


# 模拟数据库
MOCK_DATABASE = {
    "大型语言模型": [
        {
            "title": "GPT-5 发布:多模态能力再次突破",
            "snippet": "OpenAI 发布了 GPT-5，在推理和多模态理解方面取得显著进步。",
            "date": "2026-04-10",
            "url": "https://example.com/gpt5",
        },
        {
            "title": "Qwen3 开源模型系列全面升级",
            "snippet": "阿里云通义千问发布 Qwen3，在数学推理、代码生成等方面全面超越前代。",
            "date": "2026-04-08",
            "url": "https://example.com/qwen3",
        },
    ],
    "Transformer": [
        {
            "title": "Attention Is All You Need (Transformer 论文原文)",
            "snippet": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
            "date": "2017-06-12",
            "url": "https://arxiv.org/abs/1706.03762",
        },
    ],
    "BERT": [
        {
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "snippet": "We introduce a new language representation model called BERT.",
            "date": "2018-10-11",
            "url": "https://arxiv.org/abs/1810.04805",
        },
    ],
}


@mcp.tool()
def web_search(query: str, max_results: int = 3) -> str:
    """模拟联网搜索，根据关键词返回搜索结果。

    Args:
        query: 搜索关键词
        max_results: 最大返回结果数量，默认为 3
    """
    print(f"[WebSearch MCP] 收到搜索请求: {query}")

    results = []
    for key, items in MOCK_DATABASE.items():
        if key.lower() in query.lower() or query.lower() in key.lower():
            results.extend(items)

    if not results:
        results = [{
            "title": f"关于「{query}」的搜索结果",
            "snippet": f"这是关于「{query}」的模拟搜索结果。",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "url": f"https://example.com/search?q={query}",
        }]

    lines = [f"搜索「{query}」共找到 {len(results[:max_results])} 条结果:\n"]
    for i, r in enumerate(results[:max_results], 1):
        lines.append(f"{i}. 【{r['title']}】")
        lines.append(f"   摘要: {r['snippet']}")
        lines.append(f"   日期: {r['date']}")
        lines.append(f"   链接: {r['url']}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("启动 WebSearch MCP Server (stdio 模式)...")
    mcp.run(transport="stdio")
