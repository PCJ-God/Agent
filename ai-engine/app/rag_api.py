"""RAG 检索接口（Phase 3）。

POST /rag/ingest —— 摄入 docs 目录里的 Markdown（分块 + 向量化 + 写 Chroma）
POST /chat/rag   —— 检索增强对话：先检索，再流式生成，并回传引用来源
"""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import rag
from app.chat import stream_completion
from app.config import DOCS_DIR

router = APIRouter()


class IngestRequest(BaseModel):
    docs_dir: str | None = None


class RagChatRequest(BaseModel):
    query: str
    k: int = 4
    model: str | None = None


@router.post("/rag/ingest")
async def ingest(req: IngestRequest) -> dict:
    docs_dir = req.docs_dir or DOCS_DIR
    # chroma / embedding 是同步阻塞调用，丢进线程池避免卡事件循环
    return await asyncio.to_thread(rag.ingest_docs, docs_dir)


@router.post("/chat/rag")
async def chat_rag(req: RagChatRequest) -> StreamingResponse:
    messages, hits = await asyncio.to_thread(rag.build_rag_messages, req.query, req.k)

    async def event_stream():
        # 先回传引用来源，再流式生成
        sources = [
            {"source": h["source"], "header_path": h["header_path"], "score": h["score"]}
            for h in hits
        ]
        yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"
        async for ev in stream_completion(messages, req.model):
            yield ev

    return StreamingResponse(event_stream(), media_type="text/event-stream")
