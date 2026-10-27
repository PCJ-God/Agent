"""统一入口：AgentScope ReActAgent + mem0 长期记忆（agent_control 模式）。

工具集：
- search_course：LlamaIndex 检索 ACP 课程知识库（Qdrant）
- web_search：DashScope MCP 联网搜索兜底
- record_to_memory / retrieve_from_memory：agent_control 自动注册

短期记忆：InMemoryMemory（进程内，新会话清空）
长期记忆：Mem0LongTermMemory（qwen-plus + text-embedding-v4 2048 维，Qdrant）
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from urllib.parse import urlparse

from agentscope.agent import ReActAgent
from agentscope.embedding import DashScopeTextEmbedding
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory, Mem0LongTermMemory
from agentscope.message import Msg, TextBlock
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit, ToolResponse
from mem0.vector_stores.configs import VectorStoreConfig

from app import rag
from app.config import (
    DASHSCOPE_API_KEY,
    LLM_MODEL,
    MAX_AGENT_ITERS,
    MEMORY_COLLECTION,
    MEMORY_EMBED_DIM,
    QDRANT_URL,
)
from app.mcp_search import web_search

SYSTEM_PROMPT = """你是阿里云 ACP 认证学习助手，基于课程知识库回答学员的问题。

工具使用规则：
- search_course：检索 ACP 课程知识库。回答课程/考点相关问题优先用它；检索无结果或需要最新信息时，再用 web_search。
- web_search：联网搜索兜底，用于知识库没有覆盖、或需要最新信息的问题。
- record_to_memory(data)：把值得长期记住的信息（用户偏好、学习进度、易错点等）写入长期记忆。
- retrieve_from_memory(query)：回答前先判断是否需要回忆该用户过往的信息，需要时先检索长期记忆再作答。

回答要求：
- 仅依据检索到的资料作答，引用处标注编号（如 [1]）；资料不足时明确说明，不要编造。
- 回答结束后，判断本次对话有没有值得长期记住的关键信息，有就用 record_to_memory 记录。
- 用户上传的附件内容会附在问题后，需要时优先参考。
"""

_agents: dict[str, ReActAgent] = {}
_last_session: dict[str, str] = {}


# ─────────────────────── 工具 ───────────────────────

async def _search_course(query: str) -> ToolResponse:
    """检索 ACP 课程知识库（LlamaIndex + Qdrant 多路召回）。"""
    hits = await asyncio.to_thread(rag.retrieve, query, 4)
    if not hits:
        return ToolResponse(content=[TextBlock(type="text", text="知识库无相关结果")])
    parts = [
        f"[{i}] 来源《{h['source']}》 {h['header_path']}\n{h['text']}"
        for i, h in enumerate(hits, 1)
    ]
    return ToolResponse(
        content=[TextBlock(type="text", text="\n\n".join(parts))],
        metadata={
            "sources": [
                {"source": h["source"], "header_path": h["header_path"], "score": h["score"]}
                for h in hits
            ]
        },
    )


async def _web_search_tool(query: str) -> ToolResponse:
    """联网搜索兜底（DashScope MCP bailian_web_search）。"""
    text = await web_search(query)
    return ToolResponse(content=[TextBlock(type="text", text=text)])


# ─────────────────────── Agent 构建 ───────────────────────

def _qdrant_host_port() -> tuple[str, int]:
    u = urlparse(QDRANT_URL)
    return u.hostname or "qdrant", u.port or 6333


def _build_agent(user_id: str) -> ReActAgent:
    host, port = _qdrant_host_port()
    toolkit = Toolkit()
    toolkit.register_tool_function(
        _search_course,
        func_name="search_course",
        func_description="在阿里云 ACP 课程知识库中语义检索资料，返回带来源的文本切片。用于回答课程/考点相关问题。",
        json_schema={
            "type": "function",
            "function": {
                "name": "search_course",
                "description": "在阿里云 ACP 课程知识库中语义检索资料，返回带来源的文本切片。用于回答课程/考点相关问题。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "检索关键词或问题",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    )
    toolkit.register_tool_function(
        _web_search_tool,
        func_name="web_search",
        func_description="联网搜索百科知识、时事新闻等，用于本地知识库没有答案或需要最新信息时的兜底。",
        json_schema={
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "联网搜索百科知识、时事新闻等，用于本地知识库没有答案或需要最新信息时的兜底。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    )

    long_term_memory = Mem0LongTermMemory(
        agent_name="acp_assistant",
        user_name=user_id,
        model=DashScopeChatModel(model_name=LLM_MODEL, api_key=DASHSCOPE_API_KEY, stream=False),
        embedding_model=DashScopeTextEmbedding(
            api_key=DASHSCOPE_API_KEY,
            model_name="text-embedding-v4",
            dimensions=MEMORY_EMBED_DIM,
        ),
        vector_store_config=VectorStoreConfig(
            provider="qdrant",
            config={
                "collection_name": MEMORY_COLLECTION,
                "host": host,
                "port": port,
                "embedding_model_dims": MEMORY_EMBED_DIM,
                "on_disk": False,
            },
        ),
    )

    return ReActAgent(
        name="acp_assistant",
        sys_prompt=SYSTEM_PROMPT,
        model=DashScopeChatModel(model_name=LLM_MODEL, api_key=DASHSCOPE_API_KEY, stream=True),
        formatter=DashScopeChatFormatter(),
        toolkit=toolkit,
        memory=InMemoryMemory(),
        long_term_memory=long_term_memory,
        long_term_memory_mode="agent_control",
        max_iters=MAX_AGENT_ITERS,
    )


def _get_agent(user_id: str, session_id: str) -> ReActAgent:
    agent = _agents.get(user_id)
    if agent is None:
        agent = _build_agent(user_id)
        _agents[user_id] = agent
    # 新会话：清空短期记忆（长期记忆跨会话保留）
    if _last_session.get(user_id) != session_id:
        _last_session[user_id] = session_id
        try:
            agent.memory.clear()
        except Exception:
            pass
    return agent


# ─────────────────────── 流式对话 ───────────────────────

def _msg_text(msg: Msg) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    parts = []
    for b in content:
        if b.get("type") == "text":
            parts.append(b.get("text", "") or "")
    return "".join(parts)


def _msg_step(msg: Msg) -> dict | None:
    content = msg.content
    if not isinstance(content, list):
        return None
    steps = []
    for b in content:
        t = b.get("type")
        if t == "tool_use":
            steps.append(f"调用 {b.get('name', '')}")
        elif t == "tool_result":
            steps.append(f"{b.get('name', '')} 完成")
    if not steps:
        return None
    return {"type": "step", "text": "；".join(steps)}


async def run_chat(
    user_id: str,
    session_id: str,
    message: str,
    attachment_texts: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    """运行统一 Agent，产出流式事件 dict（step/delta/done/error）。"""
    agent = _get_agent(user_id, session_id)

    full = message
    if attachment_texts:
        full = message + "\n\n【附件内容】\n" + "\n\n---\n\n".join(attachment_texts)
    msg = Msg(name="user", content=full, role="user")

    queue: asyncio.Queue = asyncio.Queue()
    agent.set_msg_queue_enabled(True, queue)
    reply_task = asyncio.create_task(agent.reply(msg))

    emitted_len = 0      # 当前消息已发出的文本长度（消息内容是累计的）
    last_msg_id = None   # 用于识别新消息，切换时重置 emitted_len
    last_step_text = None  # 去重：流式下同一 tool 块会随多个 chunk 重复推送
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if reply_task.done():
                    break
                continue

            m, _last, _speech = item  # 队列项为 (msg, last, speech) 三元组
            mid = getattr(m, "id", None)
            if mid != last_msg_id:
                last_msg_id = mid
                emitted_len = 0

            step = _msg_step(m)
            if step and step["text"] != last_step_text:
                yield step
                last_step_text = step["text"]

            text = _msg_text(m)
            if len(text) > emitted_len:
                yield {"type": "delta", "text": text[emitted_len:]}
                emitted_len = len(text)
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "text": str(exc)}
        return
    finally:
        if not reply_task.done():
            reply_task.cancel()
            return

    if reply_task.exception():
        yield {"type": "error", "text": str(reply_task.exception())}
        return

    final = reply_task.result()
    text = _msg_text(final)
    if len(text) > emitted_len:
        yield {"type": "delta", "text": text[emitted_len:]}
    yield {"type": "done", "done": True}
