"""
长期记忆模块 (Mem0 + Qdrant)
跨会话持久化，支持语义搜索召回
"""
import os
from agentscope.memory import Mem0LongTermMemory
from agentscope.embedding import DashScopeTextEmbedding

from src.config import (
    DASHSCOPE_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    QDRANT_PATH,
)


def create_long_term_memory(
    collection_name: str = "agent_memories",
    enabled: bool = False,
) -> Mem0LongTermMemory | None:
    """创建长期记忆。

    Args:
        collection_name: 集合名称
        enabled: 是否启用长期记忆

    Returns:
        长期记忆实例，或 None (未启用时)
    """
    if not enabled:
        return None

    embedding = DashScopeTextEmbedding(
        api_key=DASHSCOPE_API_KEY,
        model_name=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIM,
    )

    memory = Mem0LongTermMemory(
        embedding=embedding,
        collection_name=collection_name,
        qdrant_url="http://localhost:6333",  # 或使用本地路径
        qdrant_path=QDRANT_PATH,
    )

    return memory
