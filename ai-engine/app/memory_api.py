"""记忆对话接口（Phase 5）。

POST /chat/memory —— 带短/长期记忆的对话：
  1) 从 Redis 加载该会话的短期历史（含超窗摘要）
  2) 从 Qdrant 召回该用户的长期画像事实
  3) 流式生成回答
  4) 回写短期历史 + 提炼并保存新的长期画像
"""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import memory
from app.chat import stream_completion

router = APIRouter()


class MemoryChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str
    model: str | None = None


SYSTEM = "你是阿里云 ACP 认证学习助手，回答要结合用户的长期画像与近期对话历史。"


@router.post("/chat/memory")
async def chat_memory(req: MemoryChatRequest) -> StreamingResponse:
    history = memory.get_history(req.session_id)
    summary = memory.get_summary(req.session_id)
    facts = memory.recall_facts(req.user_id, req.message)

    system_parts = [SYSTEM]
    if facts:
        system_parts.append("用户长期画像：\n- " + "\n- ".join(facts))
    if summary:
        system_parts.append("更早的对话摘要：\n" + summary)

    messages = [{"role": "system", "content": "\n\n".join(system_parts)}]
    messages += history
    messages.append({"role": "user", "content": req.message})

    async def event_stream():
        yield f"data: {json.dumps({'profile': facts}, ensure_ascii=False)}\n\n"
        answer_parts: list[str] = []
        async for ev in stream_completion(messages, req.model):
            yield ev
            # 从 delta 事件里还原完整回答，用于回写与画像提炼
            try:
                obj = json.loads(ev[len("data: "):].strip())
                if "delta" in obj:
                    answer_parts.append(obj["delta"])
            except json.JSONDecodeError:
                pass
        answer = "".join(answer_parts)

        memory.append_history(req.session_id, "user", req.message)
        memory.append_history(req.session_id, "assistant", answer)
        await memory.maybe_summarize(req.session_id)
        new_facts = await memory.extract_facts(req.message, answer)
        await asyncio.to_thread(memory.save_facts, req.user_id, new_facts)

        yield f"data: {json.dumps({'done': True, 'facts_saved': new_facts}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
