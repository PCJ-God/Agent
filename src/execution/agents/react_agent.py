"""
ReAct Agent 模块
实现思考-行动-观察循环
"""
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory, LongTermMemoryBase
from agentscope.plan import PlanNotebook
from agentscope.token import CharTokenCounter

from src.config import DASHSCOPE_API_KEY, LLM_MODEL, MAX_MEMORY_TOKENS, MAX_REACT_ITERS

# 长期记忆工具的实际签名见 agentscope 的 record_to_memory / retrieve_from_memory
LTM_PROMPT = (
    "\n\n你可以使用以下工具管理长期记忆:\n"
    "- retrieve_from_memory(keywords: list[str], limit: int = 5): "
    "按关键词从长期记忆中检索相关背景\n"
    "- record_to_memory(thinking: str, content: list[str]): "
    "把值得留存的信息写入长期记忆\n"
    "开始回答前先判断是否需要检索背景；任务结束前，主动把关键结论、"
    "用户偏好与约束写入长期记忆，供后续会话和其他成员复用。"
)


def create_react_agent(
    name: str = "Teaching Assistant",
    sys_prompt: str = "你是一个智能教学助手，擅长使用工具搜集和整理教学资料。",
    toolkit: Toolkit | None = None,
    max_iters: int | None = None,
    long_term_memory: LongTermMemoryBase | None = None,
    plan_notebook: PlanNotebook | None = None,
) -> ReActAgent:
    """创建 ReAct Agent — 全项目唯一的 Agent 装配入口。

    统一注入四件事，避免各调用点行为不一致：

    1. 历史自动压缩 (`compression_config`)
    2. 长期记忆 (`long_term_memory`，模式见下)
    3. 工具箱 (`toolkit`，由调用方按「每个 Agent 一个实例」的规则提供)
    4. 规划 (`plan_notebook`，目前只有 Leader 使用)

    Args:
        name: Agent 名称
        sys_prompt: 系统提示词
        toolkit: 工具箱；None 则创建空工具箱
        max_iters: 最大 ReAct 循环次数
        long_term_memory: 长期记忆实例。**给同一个实例即可让多个 Agent 共享一个
            记忆池** —— Mem0 检索按 metadata 匹配，同一实例意味着同一个
            agent_name，因此互相可见。
        plan_notebook: 规划笔记本。传入后 agentscope 会把 8 个计划工具
            (create_plan / update_subtask_state / view_subtasks / finish_plan ...)
            注册进 toolkit，并在每轮推理前注入当前计划提示。

    Returns:
        ReActAgent 实例
    """
    if toolkit is None:
        toolkit = Toolkit()

    if long_term_memory is not None:
        # 记忆工具本身由框架注册（docstrings 即模型看到的说明），
        # 这里补一段"何时该用"的引导，否则模型容易一次都不调用。
        sys_prompt = sys_prompt + LTM_PROMPT

    agent = ReActAgent(
        name=name,
        sys_prompt=sys_prompt,
        model=DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        ),
        toolkit=toolkit,
        formatter=DashScopeChatFormatter(),
        memory=InMemoryMemory(),
        # 历史超过阈值时由 agentscope 自动压缩为结构化摘要
        compression_config=ReActAgent.CompressionConfig(
            enable=True,
            # 不用 OpenAITokenCounter: 它首次 count() 会下载 tiktoken 词表，
            # 该地址在本机不通会直接卡死。CharTokenCounter 纯本地按字符数估算。
            agent_token_counter=CharTokenCounter(),
            trigger_threshold=MAX_MEMORY_TOKENS,
            keep_recent=3,
        ),
        long_term_memory=long_term_memory,
        # agent_control: 把 record_to_memory / retrieve_from_memory 注册成工具，
        # 由模型自己决定何时读写 —— 即"主动写入长期记忆"。
        # (默认值 both 会额外开启 static_control，每轮自动检索并自动记录，
        #  每轮多一次 LLM 调用且容易写入噪音，故显式指定。)
        long_term_memory_mode="agent_control",
        # enable_meta_tool 保持默认 False → 计划工具常驻可用，
        # 不需要模型先调 meta tool 激活工具组，行为更可预期。
        plan_notebook=plan_notebook,
        max_iters=max_iters or MAX_REACT_ITERS,
    )

    return agent
