"""
长期记忆模块 (Mem0 + Qdrant)
跨会话持久化，支持语义搜索召回 (向量化召回)
"""
import os
from agentscope.memory import Mem0LongTermMemory
from agentscope.agent import ReActAgent
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
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

    使用 Mem0 + Qdrant 向量数据库实现。每轮对话转为 Embedding 存入向量库，
    新问题时按语义相似度检索相关记忆。

    Args:
        agent_name: Agent 名称
        user_name: 用户名称
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

    vector_store = VectorStoreConfig(
        provider="qdrant",
        config={
            "on_disk": True,
            "path": QDRANT_PATH,
            "embedding_model_dims": EMBEDDING_DIM,
        }
    )

    memory = Mem0LongTermMemory(
        agent_name=agent_name,
        user_name=user_name,
        model=DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        ),
        embedding_model=embedding,
        vector_store_config=vector_store,
    )

    return memory


def create_agent_with_ltm(
    name: str,
    sys_prompt: str,
    memory: Mem0LongTermMemory,
    mode: str = "static_control",
) -> ReActAgent:
    """创建配备长期记忆的 Agent。

    Args:
        name: Agent 名称
        sys_prompt: 系统提示词
        memory: 长期记忆实例
        mode: 记忆管理模式
            - static_control: 自动保存和检索
            - agent_control: Agent 自主决定何时记/读

    Returns:
        配备长期记忆的 Agent 实例
    """
    agent = ReActAgent(
        name=name,
        sys_prompt=sys_prompt,
        model=DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        ),
        formatter=DashScopeChatFormatter(),
        memory=InMemoryMemory(),
        long_term_memory=memory,
        long_term_memory_mode=mode,
    )

    if mode == "agent_control":
        agent.sys_prompt = (
            sys_prompt + "\n\n"
            "你可以使用以下工具来管理你的长期记忆:\n"
            "- record_to_memory(data: str): 将重要信息记录到长期记忆\n"
            "- retrieve_from_memory(query: str): 根据查询从长期记忆中检索相关信息\n"
            "在回答问题前，先思考是否需要检索记忆。在对话结束后，思考是否有关键信息需要记录。"
        )

    return agent
