"""
长期记忆模块 (Mem0 + Qdrant)
跨会话持久化，支持语义搜索召回 (向量化召回)
"""
import logging
import threading

from agentscope.memory import Mem0LongTermMemory
from agentscope.model import DashScopeChatModel
from agentscope.embedding import DashScopeTextEmbedding
from mem0.vector_stores.configs import VectorStoreConfig
from qdrant_client import QdrantClient

from src.config import (
    DASHSCOPE_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    QDRANT_API_KEY,
    QDRANT_PATH,
    QDRANT_URL,
    LLM_MODEL,
)

logger = logging.getLogger(__name__)

# 本地模式的 Qdrant 是「一个存储目录同时只允许一个客户端」—— 第二个客户端
# 直接抛 RuntimeError: Storage folder ... is already accessed by another
# instance of Qdrant client。而多会话需要多个 Mem0 实例（run_id 在构造时就固定，
# 无法按调用切换），所以这里让所有实例共用同一个 QdrantClient。mem0 的
# QdrantConfig 支持注入现成 client (mem0/configs/vector_stores/qdrant.py:13)。
_qdrant_client: QdrantClient | None = None
_qdrant_lock = threading.Lock()


def _shared_qdrant_client() -> QdrantClient:
    """进程内共享的 Qdrant 客户端（首次调用时创建）。

    设了 QDRANT_URL 就走 server 模式 —— 公网部署必须这样：
      - 本地文件版是单进程独占的，多 worker 会直接抢锁失败
      - server 模式天然支持并发读写
    没设则退回本地文件（方便开发，不要用于线上）。
    """
    global _qdrant_client
    with _qdrant_lock:
        if _qdrant_client is None:
            if QDRANT_URL:
                _qdrant_client = QdrantClient(
                    url=QDRANT_URL, api_key=QDRANT_API_KEY or None
                )
                logger.info("长期记忆: Qdrant server 模式 (%s)", QDRANT_URL)
            else:
                logger.warning(
                    "长期记忆: 本地文件模式 (%s) —— 单进程独占，不要用于公网部署；"
                    "线上请设 QDRANT_URL",
                    QDRANT_PATH,
                )
                _qdrant_client = QdrantClient(path=QDRANT_PATH)
        return _qdrant_client


def create_long_term_memory(
    agent_name: str = "Agent",
    user_name: str = "user",
    session_name: str = "",
    collection_name: str = "agent_memories",
    enabled: bool = False,
) -> Mem0LongTermMemory | None:
    """创建长期记忆 (向量化召回)。

    Args:
        agent_name: Agent 名称
        user_name: 用户名称
        session_name: 会话名称，映射到 Mem0 的 run_id。空字符串 = 不限制
            会话（所有会话共用一个记忆域）
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
            # 注入共享客户端：避免每个会话各建一个而撞上 Qdrant 的目录独占锁
            "client": _shared_qdrant_client(),
            "collection_name": collection_name,
            "embedding_model_dims": EMBEDDING_DIM,
        },
    )

    memory = Mem0LongTermMemory(
        agent_name=agent_name,
        user_name=user_name,
        # Mem0 的检索作用域是 (agent_id, user_id, run_id) 三元组，写入与检索
        # 都带这三个过滤条件（_mem0_long_term_memory.py:357-359 / 668-672 /
        # 726-732）。run_id 就是「会话」这一维：传了它，各会话的记忆互不可见；
        # 传 None 则不限制会话。
        run_name=session_name or None,
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
        long_term_memory_mode="agent_control"
    )

    return memory