"""
记忆管理模块
支持短期记忆 (上下文截断/滚动摘要) 和长期记忆 (Mem0 + Qdrant)
"""
from agentscope.memory import InMemoryMemory


def create_short_term_memory(
    strategy: str = "InMemoryMemory",
    max_tokens: int = 4096,
) -> InMemoryMemory:
    """创建短期记忆。

    Args:
        strategy: 记忆策略 (InMemoryMemory / ContextTruncation)
        max_tokens: 最大 token 数

    Returns:
        短期记忆实例
    """
    # 默认使用 InMemoryMemory (AgentScope 内置的简单缓冲区)
    return InMemoryMemory()
