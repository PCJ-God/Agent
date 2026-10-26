"""纯文本对话（Phase 2）与共享的流式补全逻辑。

SSE 事件格式：
    data: {"delta": "文本增量"}
    data: {"done": true}
    data: {"error": "..."}
"""
import json

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import DASHSCOPE_API_KEY, DASHSCOPE_CHAT_URL, LLM_MODEL

router = APIRouter()


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str | None = None


async def stream_completion(messages: list[dict], model: str | None = None):
    """流式补全的 async generator：产出 SSE 事件。供 /chat 与 RAG 复用。"""
    payload = {"model": model or LLM_MODEL, "messages": messages, "stream": True}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                DASHSCOPE_CHAT_URL,
                headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0].get("delta", {}).get("content", "")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if delta:
                        yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_completion(req.messages, req.model), media_type="text/event-stream"
    )
