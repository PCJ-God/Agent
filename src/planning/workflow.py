"""
工作流编排模块
实现 5 种工作流模式: Pipeline, Branch, Parallel, MoA, HITL
"""
import asyncio
from typing import Literal
from pydantic import BaseModel, Field

from agentscope.agent import ReActAgent, UserAgent
from agentscope.tool import Toolkit, ToolResponse
from agentscope.message import Msg, TextBlock
from agentscope.pipeline import sequential_pipeline, fanout_pipeline
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter, DashScopeMultiAgentFormatter

from src.config import DASHSCOPE_API_KEY, LLM_MODEL


def _create_agent(name: str, sys_prompt: str, model_name: str = None) -> ReActAgent:
    """创建 Agent 的工厂函数。

    Args:
        name: Agent 名称
        sys_prompt: 系统提示词
        model_name: 模型名称，默认使用配置中的模型

    Returns:
        Agent 实例
    """
    return ReActAgent(
        name=name,
        sys_prompt=sys_prompt,
        model=DashScopeChatModel(
            model_name=model_name or LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        ),
        toolkit=Toolkit(),
        formatter=DashScopeChatFormatter(),
    )


async def run_pipeline_workflow(content: str) -> str:
    """模式一: 流水线 (Pipeline) - 顺序执行。

    Args:
        content: 输入内容

    Returns:
        流水线的最终输出
    """
    # 节点 A: 代码提取
    code_extractor = _create_agent(
        name="代码提取器",
        sys_prompt="你是代码提取专家。请从用户提供的文本中，精确地提取出所有 Python 代码块。只输出代码，不要有任何其他解释。",
    )

    # 节点 B: 代码验证
    code_validator = _create_agent(
        name="代码验证器",
        sys_prompt="你是代码执行与验证专家。你将接收到代码文本。请报告代码是否能成功运行，如果不能，请指出错误。",
    )

    # 节点 C: 报告生成
    report_generator = _create_agent(
        name="报告生成器",
        sys_prompt="你是审阅报告撰写助理。根据上一步的代码验证结果，生成一份简洁明了的检查报告。",
    )

    agents = [code_extractor, code_validator, report_generator]

    result = await sequential_pipeline(
        agents=agents,
        msg=Msg("user", content, "user"),
    )

    return result.content


class RouteChoice(BaseModel):
    """分支选择的结构化输出模型。"""
    choice: Literal["code_check", "style_guide", "full_review", None] = Field(
        description="根据用户意图选择分支"
    )
    extra: str | None = Field(default=None, description="对任务的简要说明")


async def run_branching_workflow(user_request: str) -> str:
    """模式二: 分支选择 (Branching) - 根据意图选择处理路径。

    Args:
        user_request: 用户请求

    Returns:
        对应分支的输出结果
    """
    # 路由 Agent
    router = _create_agent(
        name="审阅任务分发员",
        sys_prompt=(
            "你是课程审阅任务的分发员，根据用户输入选择分支:\n"
            "- 如果只是想检查代码，输出 code_check\n"
            "- 如果是想润色文笔，输出 style_guide\n"
            "- 如果是需要完整、全面的评审，输出 full_review\n"
            "仅通过结构化输出来表达你的选择，不要正文回答。"
        ),
    )

    # 分支处理 Agents
    code_checker = _create_agent(
        name="代码快检专家",
        sys_prompt="你是代码快检专家。根据用户需求，快速验证课程中的代码片段是否能运行。",
    )
    style_guide = _create_agent(
        name="语言润色专家",
        sys_prompt="你是语言润色专家。请根据用户需求，改写和润色用户提供的课程文本。",
    )
    full_review = _create_agent(
        name="首席评审",
        sys_prompt="你是首席评审。告知用户，你将启动一个包含代码、事实和教学法在内的全面评审流程。",
    )

    # 路由决策
    res = await router(Msg("user", user_request, "user"), structured_model=RouteChoice)
    choice = res.metadata.get("choice")

    if choice == "code_check":
        out = await code_checker(Msg("user", user_request, "user"))
    elif choice == "style_guide":
        out = await style_guide(Msg("user", user_request, "user"))
    else:
        out = await full_review(Msg("user", user_request, "user"))

    return out.content


async def run_parallel_workflow(content: str) -> str:
    """模式三: 并行执行 (Parallel) - 同时处理多个独立子任务。

    Args:
        content: 输入内容

    Returns:
        汇总后的输出
    """
    # 四个独立子任务的"专家" Agent
    code_checker = _create_agent(
        name="代码检查员",
        sys_prompt="验证课程中的代码是否正确无误，并给出修复建议。",
    )
    fact_checker = _create_agent(
        name="事实核查员",
        sys_prompt="核对课程中的技术概念、函数解释是否准确，引用是否规范。",
    )
    pedagogy_evaluator = _create_agent(
        name="教学法评估师",
        sys_prompt="评估课程的难度曲线、案例趣味性和练习有效性。",
    )
    style_editor = _create_agent(
        name="风格编辑",
        sys_prompt="检查并报告语言风格、术语一致性问题。",
    )

    experts = [code_checker, fact_checker, pedagogy_evaluator, style_editor]

    # 并行执行
    msgs = await fanout_pipeline(
        agents=experts,
        msg=Msg("user", content, "user"),
        enable_gather=True,
    )

    # 汇总 Agent
    summarizer = _create_agent(
        name="总编辑",
        sys_prompt="将来自多位专家的审阅意见汇总成一份结构清晰、条理分明的总审阅报告。",
    )

    merged_text = "\n\n".join([m.content for m in msgs])
    summary = await summarizer(Msg("user", merged_text, "user"))

    return summary.content


async def run_moa_workflow(task: str) -> str:
    """模式四: 混合专家 (Mixture-of-Agents, MoA) - 多模型并行追求极致质量。

    Args:
        task: 任务描述

    Returns:
        MoA 聚合后的最终输出
    """
    # 使用不同模型作为提议者
    proposer1 = _create_agent(
        name="Proposer-1",
        sys_prompt="你是一个专业的课程分析师，请为给定的课程提炼核心卖点和宣传文案。",
        model_name="qwen-plus",
    )
    proposer2 = _create_agent(
        name="Proposer-2",
        sys_prompt="你是一个专业的课程分析师，请为给定的课程提炼核心卖点和宣传文案。",
        model_name="qwen-plus",
    )
    proposer3 = _create_agent(
        name="Proposer-3",
        sys_prompt="你是一个专业的课程分析师，请为给定的课程提炼核心卖点和宣传文案。",
        model_name="qwen-plus",
    )

    proposers = [proposer1, proposer2, proposer3]

    # 并行执行所有提议者
    msgs = await fanout_pipeline(
        agents=proposers,
        msg=Msg("user", task, "user"),
        enable_gather=True,
    )

    # 聚合器
    aggregator = _create_agent(
        name="聚合器",
        sys_prompt=(
            "你的任务是综合多个大语言模型对同一问题的回答。"
            "这些回答来自不同的模型，各有优劣。请批判性地评估这些回答，"
            "识别其中的优点和不足，然后融合这些信息，生成一个高质量、准确、全面的最终回答。"
        ),
    )

    merged = "\n\n".join([f"模型 {i+1} 的回答:\n{m.content}" for i, m in enumerate(msgs)])
    final = await aggregator(Msg("user", merged, "user"))

    return final.content


async def ask_human_decision(question: str) -> ToolResponse:
    """向人类专家征求决策或意见。

    Args:
        question: 想要请人类确认或补充的具体问题
    """
    human_expert = UserAgent(name="教学专家")
    reply = await human_expert(
        Msg("assistant", question, "assistant")
    )
    return ToolResponse(
        content=[TextBlock(type="text", text=reply.get_text_content())]
    )


async def run_hitl_workflow(course_content: str) -> str:
    """模式五: 人机协作 (Human-in-the-Loop, HITL) - 人类审批节点。

    Args:
        course_content: 课程内容

    Returns:
        最终输出
    """
    # AI: 给出修改建议
    suggester = _create_agent(
        name="疑难点分析师",
        sys_prompt=(
            "你是一名资深教学设计师。请找出课程中对初学者可能最难理解的一个概念，"
            "并提供一个更通俗易懂的解释作为修改建议。"
        ),
    )

    suggestion = await suggester(Msg("user", course_content, "user"))

    # 将"人类介入"作为工具交给改写 Agent
    toolkit = Toolkit()
    toolkit.register_tool_function(ask_human_decision)

    rewriter = ReActAgent(
        name="内容改写器",
        sys_prompt=(
            "你是课程内容改写器。基于提供的 AI 建议完成最终修改。\n"
            "- 若你有把握，请直接完成修改并给出确认信息;\n"
            "- 若存在不确定、歧义或高风险，请调用工具 ask_human_decision 先向人类专家请示，"
            "再据此完成修改;\n"
            "- 在最终结果中简要说明是否咨询了人类及原因。"
        ),
        model=DashScopeChatModel(
            model_name=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
        ),
        formatter=DashScopeMultiAgentFormatter(),
        toolkit=toolkit,
    )

    task = (
        f"[课程内容]\n{course_content}\n\n"
        f"[AI 建议]\n{suggestion.content}\n"
    )

    final_action = await rewriter(Msg("user", task, "user"))
    return final_action.content
