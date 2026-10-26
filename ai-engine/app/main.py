"""ACP Copilot — AI 引擎。

Phase 2：/chat 纯文本对话（SSE 流式）。
Phase 3：/rag/ingest + /chat/rag 检索增强对话。
Phase 4：/chat/agent 工具调用。
Phase 5：/chat/memory 记忆对话。
Phase 7：/metrics 监控埋点。
"""
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app import agent_api, chat, memory_api, metrics, rag_api

app = FastAPI(title="ACP Copilot AI Engine")


@app.middleware("http")
async def count_requests(request: Request, call_next):
    metrics.inc(request.url.path)
    return await call_next(request)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ai-engine"}


@app.get("/metrics")
async def get_metrics() -> PlainTextResponse:
    return PlainTextResponse(metrics.render())


app.include_router(chat.router)
app.include_router(rag_api.router)
app.include_router(agent_api.router)
app.include_router(memory_api.router)
