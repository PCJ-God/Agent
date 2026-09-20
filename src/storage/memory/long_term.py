"""
长期记忆模块 (Mem0 + Qdrant)
跨会话持久化，支持语义搜索召回 (向量化召回)
"""
from agentscope.memory import Mem0LongTermMemory
from agentscope.model import DashScopeChatModel
from agentscope.embedding import DashScopeTextEmbedding
from mem0.vector_stores.configs import VectorStoreConfig

from src.config import (
    DASHSCOPE_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    QDRANT_PATH,
    LLM_MODEL,
)


def create_long_term_memory(
    agent_name: str = "Agent",
    user_name: str = "user",
    collection_name: str = "agent_memories",
    enabled: bool = False,
) -> Mem0LongTermMemory | None:
    """创建长期记忆 (向量化召回)。

    Args:
        agent_name: Agent 名称
        user_name: 用户名称
        collection_name: 集合名称
        enabled: 是否启用

    Returns:
        长期记忆实例，或 None
    """
    if not enabled:
        return None

    embedding = DashScopeTextEmbedding(
        api_key=DASHSCOPE_API_KEY,
        model_name=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIM,
    )

    vector_store = VectorStoreConfig(
        provider="qdrant",
        config={
            "on_disk": True,
            "path": QDRANT_PATH,
            "collection_name": collection_name,
            "embedding_model_dims": EMBEDDING_DIM,
        },
    )

    memory = Mem0LongTermMemory(
        agent_name=agent_name,
        user_name=user_name,
        model=DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
            # 必须关流式: DashScopeChatModel 默认 stream=True，流式下返回的是
            # async_generator；mem0 内部按「一次性完整响应」消费该模型
            # (取 response.choices)，会直接报
            # "'async_generator' object has no attribute ..."。
            stream=False,
        ),
        embedding_model=embedding,
        vector_store_config=vector_store,
    )

    return memory