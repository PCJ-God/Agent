"""联网搜索工具（DashScope MCP，无状态 streamable HTTP）。

DashScope 的 WebSearch MCP 无需 initialize/session，直接 POST tools/call 即可。
工具名 bailian_web_search，参数 query（必填）、count（默认 5）。
"""
import json

import httpx

from app.config import DASHSCOPE_API_KEY, MCP_SERVER_URL


async def web_search(query: str, count: int = 5) -> str:
    """联网搜索，返回「标题 + 摘要 + 链接」的纯文本（截断到 4000 字符）。"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "bailian_web_search",
            "arguments": {"query": query, "count": count},
        },
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            MCP_SERVER_URL,
            headers={
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    content = data.get("result", {}).get("content", [])
    text = "".join(item.get("text", "") for item in content if item.get("type") == "text")
    if not text:
        return "搜索无结果"

    try:
        pages = json.loads(text).get("pages", [])
    except (json.JSONDecodeError, AttributeError):
        return text[:4000]

    parts = [
        f"[{p.get('title', '')}] {p.get('snippet', '')}\n来源: {p.get('url', '')}"
        for p in pages
    ]
    return "\n\n".join(parts)[:4000]
