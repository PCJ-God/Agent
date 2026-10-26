"""记忆机制（Phase 5）。

短期记忆：Redis 列表滑动窗口，超限时用 LLM 把旧消息压缩成摘要。
长期记忆：LLM 提炼用户画像事实 -> 向量化 -> 存 Qdrant -> 跨会话按相似度召回。
"""
import asyncio
import json
from uuid import uuid4

import httpx
import redis

from app import rag
from app.config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_CHAT_URL,
    LLM_MODEL,
    MEMORY_SUMMARY_KEEP,
    MEMORY_WINDOW,
    QDRANT_URL,
    REDIS_ADDR,
)

PROFILE_COLLECTION = "user_profile"


def _redis() -> redis.Redis:
    host, _, port = REDIS_ADDR.partition(":")
    return redis.Redis(host=host, port=int(port or 6379), decode_responses=True)


# ─────────────────────── 短期记忆（Redis 滑动窗口） ───────────────────────

def get_history(session_id: str, limit: int | None = None) -> list[dict]:
    items = _redis().lrange(f"chat:hist:{session_id}", 0, -1)
    msgs = [json.loads(x) for x in items]
    return msgs[-limit:] if limit else msgs


def append_history(session_id: str, role: str, content: str) -> None:
    r = _redis()
    r.rpush(f"chat:hist:{session_id}", json.dumps({"role": role, "content": content}, ensure_ascii=False))
    r.ltrim(f"chat:hist:{session_id}", -MEMORY_WINDOW, -1)


def set_summary(session_id: str, summary: str) -> None:
    _redis().set(f"chat:summary:{session_id}", summary)


def get_summary(session_id: str) -> str:
    return _redis().get(f"chat:summary:{session_id}") or ""


# ─────────────────────── 长期记忆（Qdrant 用户画像） ───────────────────────

def _ensure_collection(dim: int) -> None:
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{QDRANT_URL}/collections/{PROFILE_COLLECTION}")
        if r.status_code == 404:
            c.put(
                f"{QDRANT_URL}/collections/{PROFILE_COLLECTION}",
                json={"vectors": {"size": dim, "distance": "Cosine"}},
            )


def save_facts(user_id: str, facts: list[str]) -> None:
    """把用户画像事实向量化后写入 Qdrant（带 user_id 隔离）。"""
    facts = [f for f in facts if f.strip()]
    if not facts:
        return
    embs = rag.embed_texts(facts)
    _ensure_collection(len(embs[0]))
    points = [
        {"id": str(uuid4()), "vector": e, "payload": {"user_id": user_id, "fact": f}}
        for f, e in zip(facts, embs)
    ]
    with httpx.Client(timeout=30) as c:
        c.put(f"{QDRANT_URL}/collections/{PROFILE_COLLECTION}/points?wait=true", json={"points": points})


def recall_facts(user_id: str, query: str, k: int = 4) -> list[str]:
    """按用户召回与当前问题最相关的画像事实。"""
    emb = rag.embed_texts([query])[0]
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{QDRANT_URL}/collections/{PROFILE_COLLECTION}/points/search",
            json={
                "vector": emb,
                "limit": k,
                "filter": {"must": [{"key": "user_id", "match": {"value": user_id}}]},
                "with_payload": True,
            },
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return [p["payload"]["fact"] for p in r.json()["result"]]


# ─────────────────────── LLM 辅助 ───────────────────────

async def _complete(prompt: str) -> str:
    """非流式补全，用于摘要压缩与画像提炼。"""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            DASHSCOPE_CHAT_URL,
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
            json={"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}]},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def extract_facts(user_msg: str, assistant_msg: str) -> list[str]:
    prompt = (
        "从下面的对话中提炼关于用户的长期画像（学习基础、易错点、目标、偏好等）。"
        "每行一条，只写确定的事实，没有就返回空。\n"
        f"用户：{user_msg}\n助手：{assistant_msg}"
    )
    text = await _complete(prompt)
    return [line.lstrip("- ").strip() for line in text.splitlines() if line.strip()][:5]


async def maybe_summarize(session_id: str) -> None:
    """历史超窗时，把最早的一批消息压缩成摘要，只保留最近几条原文。"""
    hist = get_history(session_id)
    if len(hist) <= MEMORY_WINDOW:
        return
    old = hist[: -MEMORY_SUMMARY_KEEP]
    if not old:
        return
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in old)
    summary = await _complete(f"把下面的对话历史压缩成简短摘要（保留关键信息、用户偏好）：\n{transcript}")
    prev = get_summary(session_id)
    set_summary(session_id, (prev + "\n" + summary).strip())
    r = _redis()
    r.ltrim(f"chat:hist:{session_id}", -MEMORY_SUMMARY_KEEP, -1)
