"""
短期记忆模块
实现三种策略: InMemoryMemory / ContextTruncation / RollingSummary
"""
from agentscope.memory import InMemoryMemory, MemoryBase
from agentscope.message import Msg
from agentscope.model import DashScopeChatModel
from agentscope.token import OpenAITokenCounter
from agentscope.formatter import DashScopeChatFormatter

from src.config import DASHSCOPE_API_KEY, LLM_MODEL, MAX_MEMORY_TOKENS


def create_short_term_memory(
    strategy: str = "InMemoryMemory",
    max_tokens: int = None,
    buffer_size: int = 10,
    summary_ratio: float = 0.5,
) -> InMemoryMemory | MemoryBase:
    """创建短期记忆。

    Args:
        strategy: 记忆策略
            - InMemoryMemory: 简单缓冲区，保留所有对话
            - ContextTruncation: 固定窗口截断 (通过 Formatter 的 max_tokens 实现)
            - RollingSummary: 滚动摘要 (超出 buffer_size 时压缩旧对话为摘要)
        max_tokens: 最大 token 数 (用于 ContextTruncation)
        buffer_size: 缓冲区大小 (用于 RollingSummary)
        summary_ratio: 摘要压缩比例 (用于 RollingSummary)

    Returns:
        短期记忆实例
    """
    max_tokens = max_tokens or MAX_MEMORY_TOKENS

    if strategy == "ContextTruncation":
        return create_truncated_formatter(max_tokens=max_tokens)

    elif strategy == "RollingSummary":
        return RollingSummaryMemory(
            buffer_size=buffer_size,
            summary_ratio=summary_ratio,
        )

    else:
        return InMemoryMemory()


def create_truncated_formatter(max_tokens: int = None) -> DashScopeChatFormatter:
    """创建带截断功能的 Formatter。

    AgentScope 的 Formatter 在格式化消息时会自动检查 token 长度，
    超出 max_tokens 时从开头丢弃最早的对话。

    Args:
        max_tokens: 最大 token 数

    Returns:
        带截断功能的 Formatter 实例
    """
    max_tokens = max_tokens or MAX_MEMORY_TOKENS
    return DashScopeChatFormatter(
        token_counter=OpenAITokenCounter(model_name="gpt-4"),
        max_tokens=max_tokens,
    )


class RollingSummaryMemory(MemoryBase):
    """滚动摘要记忆。

    当对话历史超过 buffer_size 时，调用 LLM 将旧对话压缩为摘要。
    对应课程中的 Rolling Summary 策略。
    """

    def __init__(self, buffer_size: int = 10, summary_ratio: float = 0.5):
        super().__init__()
        self.history: list[Msg] = []
        self.buffer_size = buffer_size
        self.summary_ratio = summary_ratio
        self._summary: str = ""
        self._llm = DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        )

    async def add(self, msg: Msg) -> None:
        """添加消息，可能触发摘要压缩。

        Args:
            msg: 要添加的消息
        """
        self.history.append(msg)
        await self.try_summarize()

    async def get_memory(self) -> list[Msg]:
        """获取记忆 (包含摘要)。

        Returns:
            消息列表，第一条为摘要消息 (如果存在)
        """
        result = []
        if self._summary:
            result.append(Msg("system", f"【历史摘要】{self._summary}", "system"))
        result.extend(self.history)
        return result

    async def try_summarize(self) -> None:
        """尝试压缩旧对话为摘要。"""
        if len(self.history) > self.buffer_size:
            # 1. 确定要摘要的部分
            num_to_summarize = max(1, int(len(self.history) * self.summary_ratio))
            messages_to_summarize = self.history[:num_to_summarize]

            # 2. 调用大模型生成摘要
            summary_prompt = "请将以下对话历史总结为一段简洁的摘要，保留关键信息和决策:\n\n"
            for m in messages_to_summarize:
                content = m.content if isinstance(m.content, str) else str(m.content)
                summary_prompt += f"[{m.role}] {m.name}: {content}\n"

            try:
                response = await self._llm(
                    messages=[Msg("user", summary_prompt, "user")]
                )
                if response:
                    content = response.content if hasattr(response, 'content') else str(response)
                    if isinstance(response, list) and len(response) > 0:
                        content = response[0].get("content", "") if isinstance(response[0], dict) else str(response[0])
                    self._summary = content if content else self._summary
            except Exception:
                pass  # 摘要失败时保留旧摘要

            # 3. 用摘要替换原始对话
            self.history = self.history[num_to_summarize:]

    async def clear(self) -> None:
        """清空记忆。"""
        self.history = []
        self._summary = ""
