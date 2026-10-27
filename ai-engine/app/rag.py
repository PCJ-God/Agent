"""RAG 检索管线：LlamaIndex（QdrantVectorStore + BM25Retriever + DashScopeRerank）。

- 摄入：标题感知分块（header_path 溯源）→ DashScope 嵌入（分批，httpx 直连）→ Qdrant
- 检索：向量召回 + BM25 关键词召回 → RRF 融合 → 可选 gte-rerank 重排
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx
import jieba
from llama_index.core.schema import TextNode
from llama_index.core.vector_stores import VectorStoreQuery
from llama_index.postprocessor.dashscope_rerank import DashScopeRerank
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.config import (
    DASHSCOPE_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_URL,
    QDRANT_URL,
    RAG_COLLECTION,
    RERANK_ENABLED,
    RERANK_MODEL,
)

VECTOR_TOP_K = 12   # 向量召回候选数
BM25_TOP_K = 12     # 关键词召回候选数
FUSION_TOP_K = 8    # RRF 融合后候选数
EMBED_BATCH = 8     # DashScope 嵌入单批上限 10，留余量


# 模块级状态：全部节点（供 BM25）+ BM25 检索器
_all_nodes: list[TextNode] = []
_bm25: BM25Retriever | None = None


# ─────────────────────── 嵌入（分批） ───────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    with httpx.Client(timeout=60) as client:
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            resp = client.post(
                EMBEDDING_URL,
                headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
                json={"model": EMBEDDING_MODEL, "input": batch},
            )
            resp.raise_for_status()
            items = sorted(resp.json()["data"], key=lambda x: x["index"])
            out.extend(it["embedding"] for it in items)
    return out


def _zh_tokenizer(text: str) -> list[str]:
    return [t for t in jieba.cut(text) if t.strip()]


# ─────────────────────── 分块 ───────────────────────

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


def _to_nodes(chunks: list[dict]) -> list[TextNode]:
    return [
        TextNode(
            text=ch["text"],
            id_=str(uuid4()),  # Qdrant 点 ID 仅接受 uint 或 UUID
            metadata={"source": ch["source"], "header_path": ch["header_path"]},
        )
        for ch in chunks
    ]


# ─────────────────────── 摄入 ───────────────────────

def _vector_store() -> QdrantVectorStore:
    return QdrantVectorStore(
        collection_name=RAG_COLLECTION,
        client=QdrantClient(url=QDRANT_URL),
    )


def _rebuild_bm25() -> None:
    global _bm25
    _bm25 = BM25Retriever.from_defaults(
        nodes=_all_nodes,
        similarity_top_k=BM25_TOP_K,
        tokenizer=_zh_tokenizer,
    )


def ingest_docs(docs_dir: str) -> dict:
    """清空重建：把 docs_dir 下所有 .md 分块、向量化、写入 Qdrant。"""
    global _all_nodes
    docs_dir = Path(docs_dir)
    if not docs_dir.is_dir():
        return {"ingested": 0, "error": f"docs dir not found: {docs_dir}"}

    chunks: list[dict] = []
    for md in sorted(docs_dir.glob("*.md")):
        chunks.extend(_chunk_markdown(md.read_text(encoding="utf-8"), md.name))
    if not chunks:
        return {"ingested": 0}

    _all_nodes = _to_nodes(chunks)
    embs = embed_texts([n.get_content() for n in _all_nodes])
    for n, e in zip(_all_nodes, embs):
        n.embedding = e

    client = QdrantClient(url=QDRANT_URL)
    if client.collection_exists(RAG_COLLECTION):
        client.delete_collection(RAG_COLLECTION)
    _vector_store().add(_all_nodes)
    _rebuild_bm25()

    return {
        "ingested": len(_all_nodes),
        "sources": sorted({n.metadata["source"] for n in _all_nodes}),
    }


def ingest_text(name: str, text: str, source: str | None = None) -> dict:
    """追加单篇文档（worker / 管理员入库调用）。"""
    global _all_nodes
    chunks = _chunk_markdown(text, source or name)
    if not chunks:
        return {"ingested": 0}

    nodes = _to_nodes(chunks)
    embs = embed_texts([n.get_content() for n in nodes])
    for n, e in zip(nodes, embs):
        n.embedding = e

    _vector_store().add(nodes)
    _all_nodes.extend(nodes)
    _rebuild_bm25()
    return {"ingested": len(nodes)}


# ─────────────────────── 检索 ───────────────────────

def _rrf(result_lists: list[list[TextNode]], k: int = 60) -> list[tuple[TextNode, float]]:
    """倒数排名融合（RRF），返回 (节点, 融合分)。"""
    scores: dict[str, float] = {}
    by_id: dict[str, TextNode] = {}
    for nodes in result_lists:
        for rank, n in enumerate(nodes):
            scores[n.node_id] = scores.get(n.node_id, 0.0) + 1.0 / (k + rank + 1)
            by_id[n.node_id] = n
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(by_id[nid], s) for nid, s in ranked]


def retrieve(query: str, k: int = 4) -> list[dict]:
    if not _all_nodes:
        return []

    # 1) 向量召回（语义）
    q_emb = embed_texts([query])[0]
    vs_query = VectorStoreQuery(query_embedding=q_emb, similarity_top_k=VECTOR_TOP_K)
    vec_nodes = list(_vector_store().query(vs_query).nodes or [])

    # 2) BM25 关键词召回
    bm_nodes = [n for n in (_bm25.retrieve(query) if _bm25 else [])]

    # 3) RRF 融合
    pairs = _rrf([vec_nodes, bm_nodes])[:FUSION_TOP_K]
    fused = [n for n, _ in pairs]
    rrf_scores = {n.node_id: s for n, s in pairs}

    # 4) 重排（可选）
    scored: list[tuple[TextNode, float]]
    if fused and RERANK_ENABLED:
        reranker = DashScopeRerank(
            top_n=min(k, len(fused)), model=RERANK_MODEL, api_key=DASHSCOPE_API_KEY
        )
        ranked = reranker.postprocess_nodes(fused, query_str=query)
        scored = [(r.node, r.score) for r in ranked[:k]]
    else:
        scored = [(n, rrf_scores.get(n.node_id, 0.0)) for n in fused[:k]]

    return [
        {
            "text": n.get_content(),
            "source": n.metadata.get("source", ""),
            "header_path": n.metadata.get("header_path", ""),
            "score": round(s, 4),
        }
        for n, s in scored
    ]
