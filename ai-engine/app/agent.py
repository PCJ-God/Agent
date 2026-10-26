"""Agent 与工具调用（Phase 4）。

基于 DashScope 兼容接口的函数调用（function-calling）实现 ReAct 循环：
    思考 → 调用工具（RAG 检索 / 联网搜索）→ 观察结果 → 循环 → 最终回答。

工具：
    search_knowledge_base —— 本地 ACP 知识库语义检索（Chroma）
    web_search            —— 联网搜索兜底（DashScope MCP bailian_web_search）
"""
import asyncio
import json

import httpx

from app import rag
from app.config import DASHSCOPE_API_KEY, DASHSCOPE_CHAT_URL, LLM_MODEL, MAX_AGENT_ITERS
from app.mcp_search import web_search

SYSTEM_PROMPT = (
    "你是阿里云 ACP 认证学习助手。回答流程："
    "1) 优先调用 search_knowledge_base 检索本地知识库；"
    "2) 本地知识库没有答案、或问题需要最新信息时，调用 web_search 联网搜索兜底；"
    "3) 基于工具返回的资料组织回答，并标注信息来源。不要编造资料里没有的内容。"
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "在本地 ACP 知识库中语义检索资料，返回带来源的文本切片",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索百科知识、时事新闻等，用于本地知识库没有答案时的兜底",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"],
            },
        },
    },
]


async def _chat_completion(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """非流式对话补全（Agent 循环内使用）。"""
    payload = {"model": LLM_MODEL, "messages": messages}
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            DASHSCOPE_CHAT_URL,
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def _execute_tool(name: str, args: dict) -> str:
    if name == "search_knowledge_base":
        hits = await asyncio.to_thread(rag.retrieve, args.get("query", ""), 4)
        return json.dumps(
            [
                {
                    "source": h["source"],
                    "header_path": h["header_path"],
                    "text": h["text"],
                }
                for h in hits
            ],
            ensure_ascii=False,
        )
    if name == "web_search":
        return await web_search(args.get("query", ""))
    return f"未知工具: {name}"


async def run_agent(query: str, max_iters: int | None = None) -> tuple[str, list[dict]]:
    """跑 ReAct 循环，返回 (最终回答, 工具调用轨迹)。"""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    steps: list[dict] = []

    for _ in range(max_iters or MAX_AGENT_ITERS):
        data = await _chat_completion(messages, TOOLS)
        msg = data["choices"][0]["message"]

        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            messages.append(msg)  # assistant 消息（含 tool_calls）
            for tc in tool_calls:
                fn = tc["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await _execute_tool(fn["name"], args)
                steps.append({
                    "tool": fn["name"],
                    "args": args,
                    "result_preview": result[:200],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result,
                })
            continue

        return msg.get("content") or "", steps

    return "已达到最大推理轮数，仍未能给出确定回答。", steps
