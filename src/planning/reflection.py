"""
反思模式模块
实现 Self-Review (自我反馈) 和 External Feedback (外部验证) 两种反思模式
"""
import asyncio
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit, ToolResponse, execute_python_code
from agentscope.message import Msg, TextBlock
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter

from src.config import DASHSCOPE_API_KEY, LLM_MODEL


def create_writer_agent() -> ReActAgent:
    """创建写作 Agent (装备代码解释器工具)。

    Returns:
        写作 Agent 实例
    """
    toolkit = Toolkit()
    toolkit.register_tool_function(execute_python_code)

    return ReActAgent(
        name="Writer",
        sys_prompt=(
            "你是一位技术课程作家，负责润色 Jupyter Notebook 课程。\n"
            "任务要求:\n"
            "1. 优化文本表达，使其更流畅生动\n"
            "2. 绝对不要修改代码中的变量名、函数名、参数名\n"
            "3. 润色后，使用 execute_python_code 工具验证所有代码块\n"
            "4. 如果代码执行失败，检查是否意外修改了代码并修正\n"
            "记住: 只改文案，不改代码逻辑!"
        ),
        model=DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        ),
        toolkit=toolkit,
        formatter=DashScopeChatFormatter(),
        max_iters=10,
    )


def create_reviewer_agent() -> ReActAgent:
    """创建审查 Agent (独立的技术审查员)。

    Returns:
        审查 Agent 实例
    """
    return ReActAgent(
        name="Reviewer",
        sys_prompt=(
            "你是一个严苛的技术审查员。你的任务是审查润色后的课程内容，确保:\n"
            "1. 润色后的课程符合写作规范\n"
            "2. 代码、配置、数据等技术内容没有被意外修改\n\n"
            "请比对原始内容和润色后内容:\n"
            "- 如果只修改了文案表达，代码等技术内容完全一致，就回答'通过'\n"
            "- 如果发现任何技术内容被修改，就回答'不通过'，并指出具体是哪处内容被意外修改了"
        ),
        model=DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        ),
        toolkit=Toolkit(),
        formatter=DashScopeChatFormatter(),
    )


async def self_review_mode(original_content: str, draft_content: str) -> str:
    """自我反馈模式: 两个 Agent 分别负责生成和审查。

    Args:
        original_content: 原始内容
        draft_content: 初稿内容

    Returns:
        审查结果和修改建议
    """
    reviewer = create_reviewer_agent()

    review_msg = Msg(
        name="user",
        content=(
            f"请审查以下润色后的内容是否与原始内容在技术层面保持一致。\n\n"
            f"【原始内容】:\n{original_content}\n\n"
            f"【润色后内容】:\n{draft_content}"
        ),
        role="user",
    )

    result = await reviewer(review_msg)
    return result.content # type: ignore


async def external_feedback_mode(original_content: str) -> str:
    """外部反馈模式: Agent 装备代码解释器，自动验证代码正确性。

    Args:
        original_content: 包含代码的原始内容

    Returns:
        Agent 的最终输出 (润色后的内容 + 验证结果)
    """
    writer = create_writer_agent()

    user_msg = Msg(
        name="user",
        content=(
            f"请润色以下课程内容，要求:\n"
            f"1. 让文案更生动易懂\n"
            f"2. 不要修改代码中的变量名、函数名\n"
            f"3. 润色后用 execute_python_code 验证代码能否运行\n"
            f"4. 如果报错，说明你可能改错了代码，请修正\n\n"
            f"【课程内容】:\n{original_content}"
        ),
        role="user",
    )

    result = await writer(user_msg)
    return result.content # type: ignore
