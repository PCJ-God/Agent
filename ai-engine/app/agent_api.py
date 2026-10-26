"""Agent 对话接口（Phase 4）。

POST /chat/agent —— ReAct 循环（RAG 工具 + 联网搜索兜底），
先回传工具调用轨迹，再回传最终回答。
"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import agent

router = APIRouter()


class AgentChatRequest(BaseModel):
    query: str
    max_iters: int | None = None


@router.post("/chat/agent")
async def chat_agent(req: AgentChatRequest) -> StreamingResponse:
    answer, steps = await agent.run_agent(req.query, req.max_iters)

    async def event_stream():
        yield f"data: {json.dumps({'steps': steps}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'answer': answer}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
