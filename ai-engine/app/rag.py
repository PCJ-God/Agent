"""RAG 检索管线（Phase 3）。

文档摄入 → 结构感知分块 → 向量化（DashScope text-embedding-v4）→ 写入 Chroma
→ 语义检索。生成侧在 rag_api.py 里把检索结果拼进 prompt，并带 [i] 引用编号。
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import chromadb
import httpx

from app.config import CHROMA_URL, DASHSCOPE_API_KEY, EMBEDDING_MODEL, EMBEDDING_URL

COLLECTION_NAME = "acp_docs"


def _chunk_markdown(text: str, source: str) -> list[dict]:
    """按标题层级切块，写入 header_path 溯源元数据。"""
    chunks: list[dict] = []
    headers: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            chunks.append({
                "text": body,
                "header_path": " > ".join(headers) if headers else source,
                "source": source,
            })
        buf.clear()

    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip()
            headers = headers[: level - 1] + [title]
        elif line.strip():
            buf.append(line)
    flush()
    return chunks


EMBED_BATCH_SIZE = 8  # DashScope 嵌入接口单批上限 10 条，留余量


def embed_texts(texts: list[str]) -> list[list[float]]:
    """用 DashScope 兼容接口批量向量化（服务端单批上限 10 条，分批调用）。"""
    embeddings: list[list[float]] = []
    with httpx.Client(timeout=60) as client:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i:i + EMBED_BATCH_SIZE]
            resp = client.post(
                EMBEDDING_URL,
                headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
                json={"model": EMBEDDING_MODEL, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()
            items = sorted(data["data"], key=lambda x: x["index"])
            embeddings.extend(it["embedding"] for it in items)
    return embeddings


def _get_collection():
    """Chroma 集合（余弦相似度）。host/port 从 CHROMA_URL 解析。"""
    u = urlparse(CHROMA_URL)
    client = chromadb.HttpClient(host=u.hostname, port=u.port or 8000)
    return client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def ingest_docs(docs_dir: str) -> dict:
    """把 docs_dir 下所有 .md 分块、向量化、写入 Chroma（幂等：清空重建）。"""
    docs_dir = Path(docs_dir)
    if not docs_dir.is_dir():
        return {"ingested": 0, "error": f"docs dir not found: {docs_dir}"}

    rows: list[dict] = []
    for md in sorted(docs_dir.glob("*.md")):
        rows.extend(_chunk_rows(md.name, md.read_text(encoding="utf-8")))

    if not rows:
        return {"ingested": 0}

    n = _add_rows(rows, clear=True)
    return {
        "ingested": n,
        "sources": sorted({r["metadata"]["source"] for r in rows}),
    }


def _chunk_rows(name: str, text: str, source: str | None = None) -> list[dict]:
    """把单篇文档内容分块成待写入的行。name 用于唯一 ID，source 用于溯源标签。"""
    rows: list[dict] = []
    for i, ch in enumerate(_chunk_markdown(text, source or name)):
        rows.append({
            "id": f"{name}-{i}",
            "document": f"{ch['header_path']}\n\n{ch['text']}",
            "metadata": {"source": ch["source"], "header_path": ch["header_path"]},
        })
    return rows


def _add_rows(rows: list[dict], clear: bool = False) -> int:
    """把分块写入 Chroma。clear=True 时先清空集合（幂等重建）。"""
    if not rows:
        return 0
    col = _get_collection()
    if clear:
        existing = col.get()["ids"]
        if existing:
            col.delete(ids=existing)
    col.add(
        ids=[r["id"] for r in rows],
        documents=[r["document"] for r in rows],
        embeddings=embed_texts([r["document"] for r in rows]),
        metadatas=[r["metadata"] for r in rows],
    )
    return len(rows)


def ingest_text(name: str, text: str, source: str | None = None) -> dict:
    """把单篇文档内容追加写入 Chroma（供异步解析 worker 调用）。"""
    rows = _chunk_rows(name, text, source)
    return {"ingested": _add_rows(rows)}


def retrieve(query: str, k: int = 4) -> list[dict]:
    """语义检索，返回 top-k 切片（带溯源元数据与相似度）。"""
    emb = embed_texts([query])[0]
    col = _get_collection()
    res = col.query(
        query_embeddings=[emb], n_results=k, include=["documents", "metadatas", "distances"]
    )
    out: list[dict] = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append({
            "text": doc,
            "source": meta.get("source", ""),
            "header_path": meta.get("header_path", ""),
            "score": round(1 - dist, 4),  # cosine distance -> similarity
        })
    return out


def build_rag_messages(query: str, k: int = 4) -> tuple[list[dict], list[dict]]:
    """检索并拼出带引用的 messages。返回 (messages, hits)。"""
    hits = retrieve(query, k)
    if not hits:
        return [{"role": "user", "content": query}], []

    parts = [
        f"[{i}] 来源《{h['source']}》 {h['header_path']}\n{h['text']}"
        for i, h in enumerate(hits, 1)
    ]
    context = "\n\n".join(parts)
    system = (
        "你是阿里云 ACP 认证学习助手。请仅依据下面给出的资料回答问题，"
        "在引用处标注编号（如 [1]）。资料不足以回答时，明确说资料不足，不要编造。"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"资料：\n{context}\n\n问题：{query}"},
    ]
    return messages, hits
