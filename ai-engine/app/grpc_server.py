"""gRPC 服务：AssistantService 实现（Chat 流式 / IngestText / Reindex）。"""
from __future__ import annotations

import asyncio

import redis

from app import assistant, rag
from app.config import DOCS_DIR, REDIS_URL
from gen import assistant_pb2, assistant_pb2_grpc


def _get_parse_result(task_id: str) -> str:
    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        return r.get(f"parse:{task_id}") or ""
    except Exception:
        return ""


class AssistantServicer(assistant_pb2_grpc.AssistantServiceServicer):
    async def Chat(self, request, context):
        texts = []
        for tid in request.task_ids:
            t = _get_parse_result(tid)
            if t:
                texts.append(t)

        async for ev in assistant.run_chat(
            request.user_id,
            request.session_id,
            request.message,
            texts,
        ):
            event = assistant_pb2.ChatEvent(
                type=ev.get("type", ""),
                text=ev.get("text", ""),
                done=ev.get("done", False),
            )
            for s in ev.get("sources", []):
                event.sources.append(
                    assistant_pb2.Source(
                        source=s["source"],
                        header_path=s["header_path"],
                        score=s["score"],
                    )
                )
            yield event

    async def IngestText(self, request, context):
        result = await asyncio.to_thread(
            rag.ingest_text, request.name, request.text, request.source
        )
        return assistant_pb2.IngestTextResponse(ingested=int(result.get("ingested", 0)))

    async def Reindex(self, request, context):
        docs_dir = request.docs_dir or DOCS_DIR
        result = await asyncio.to_thread(rag.ingest_docs, docs_dir)
        return assistant_pb2.ReindexResponse(
            ingested=int(result.get("ingested", 0)),
            sources=list(result.get("sources", [])),
        )
