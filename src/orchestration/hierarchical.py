"""
层级协作模式 (Hierarchical) — 调度层核心
Leader Agent 负责任务拆分和优先级分配，通过 Handoff 调度 Member Agents

四层架构定位:
- 接入层 → 接收用户请求
- 调度层 (本模块) → 任务拆解、优先级排序、调度执行
- 执行层 → Agent 执行 + MCP 工具调用 + Skill 加载
- 存储层 → 记忆持久化 + 结果输出
"""
import asyncio
import logging

from agentscope.agent import ReActAgent
from agentscope.message import Msg, TextBlock
from agentscope.plan import PlanNotebook
from agentscope.tool import ToolResponse, Toolkit

from src.config import ENABLE_LONG_TERM_MEMORY, HISTORY_REPLAY_TURNS, LTM_SCOPE
from src.execution.agents.agent_factory import (
    create_research_agent,
    create_review_agent,
)
from src.execution.agents.react_agent import create_react_agent
from src.execution.tools.tool_manager import ToolPool, create_mcp_client
from src.storage.memory.long_term import create_long_term_memory
from src.storage.memory.session_store import append_turn, ensure_session, recent_turns

logger = logging.getLogger(__name__)

LEADER_PROMPT = (
    "你是一个项目负责人 (调度层)，负责协调和分配任务。\n"
    "你的团队成员 (执行层):\n"
    "- invoke_researcher: 研究助手，负责搜集资料\n"
    "- invoke_reviewer: 审查专家，负责质量审查\n\n"
    "工作流程:\n"
    "1. 分析用户需求，拆解为子任务\n"
    "2. 确定子任务优先级\n"
    "3. 依次调用团队成员执行\n"
    "4. 汇总结果并交付最终输出\n\n"
    "对于需要多步骤才能完成的任务，用计划工具把计划显式写下来"
    "(create_plan 建计划 / update_subtask_state 推进状态 / "
    "finish_subtask 收尾子任务 / finish_plan 结束计划)，再按计划逐步推进，"
    "而不是只在心里盘算。"
)


def _create_shared_long_term_memory(session_id: str = "", user_id: str = "local"):
    """创建共享的长期记忆；失败降级为 None，不阻断团队启动。

    Args:
        session_id: 会话（任务）ID。LTM_SCOPE=session 时映射到 Mem0 的
            run_id，使同一用户的不同任务之间互相隔离。
        user_id: 用户 ID，映射到 Mem0 的 user_id —— **多用户隔离的根本**。
            公网部署下必须是认证层给出的真实用户，绝不能用常量，
            否则所有用户的记忆会落进同一个池子。

    Returns:
        Mem0LongTermMemory 实例，或 None
    """
    if not ENABLE_LONG_TERM_MEMORY:
        logger.info("长期记忆未启用 (ENABLE_LONG_TERM_MEMORY=false)")
        return None

    try:
        # 三个 Agent 共用同一个实例 = 同一个记忆池。
        # Mem0 检索按 metadata 匹配，所以 agent_name 用团队名而不是各自的
        # Agent 名字 —— 否则研究员写入的记忆会被 Leader 的检索直接过滤掉。
        # 隔离维度: user_id(谁) + run_id(哪个任务)；agent_id 是团队名，不是用户维度。
        session_name = session_id if LTM_SCOPE == "session" else ""
        return create_long_term_memory(
            agent_name="TeachingTeam",
            user_name=user_id,
            session_name=session_name,
            enabled=True,
        )
    except Exception as e:
        logger.warning("长期记忆初始化失败: %s，将不带长期记忆运行", e)
        return None


class HierarchicalTeam:
    """层级协作团队。

    架构:
        Leader (调度层)
        ├── Researcher (执行层 - 研究助手)
        └── Reviewer  (执行层 - 质量审查)

    三个 Agent 都具备: 历史自动压缩 + 长期记忆(可主动读写) + 远程 MCP 工具与 Skill。
    规划能力 (PlanNotebook) 只给 Leader —— 它是任务的拆解者与调度者。

    一个 HierarchicalTeam 实例 = 某个用户在某个会话（任务）下的团队。
    隔离有三个维度：进程、用户 (user_id)、任务 (session_id)。
    长期记忆的隔离靠 Mem0 的 (agent_id, user_id, run_id) 三元组 ——
    其中 user_id 是多用户场景的根本，绝不能是常量。

    请用 `await HierarchicalTeam.create(session_id, user_id)` 装配，不要直接实例化。
    """

    def __init__(self) -> None:
        self.session_id = ""
        self.user_id = "local"
        self.mcp_client = None
        self.long_term_memory = None
        self.tool_pool: ToolPool | None = None
        # 以下三者由 _build() 装配。只声明类型不赋 None，
        # 是为了让调用点（invoke_* / chat / enable_streaming）不必处处判空 ——
        # 前提是必须用 `await HierarchicalTeam.create()`，不要直接实例化。
        self.researcher: ReActAgent
        self.reviewer: ReActAgent
        self.leader: ReActAgent

    @classmethod
    async def create(
        cls, session_id: str = "", user_id: str = "local"
    ) -> "HierarchicalTeam":
        """装配团队（异步：需要建立 MCP 客户端并抓取工具）。

        Args:
            session_id: 会话（任务）ID。同一用户的不同任务之间完全隔离。
            user_id: 用户 ID。不同用户的团队在任何层面都不共享东西。

        Returns:
            装配完成的 HierarchicalTeam
        """
        team = cls()
        await team._build(session_id, user_id)
        return team

    async def _build(self, session_id: str = "", user_id: str = "local") -> None:
        # ── 共享资源 ──
        # MCP 客户端与工具池全队共用一份（客户端无状态，没有连接需要释放）。
        self.session_id = session_id
        self.user_id = user_id
        self.mcp_client = await create_mcp_client()
        self.long_term_memory = _create_shared_long_term_memory(session_id, user_id)
        self.tool_pool = await ToolPool.create(self.mcp_client)

        # ── 执行层: Member Agents ──
        # 注意 new_toolkit() 是「从池里复制一份」，不是共享同一个 Toolkit ——
        # Agent 会往 toolkit 里注册 plan/记忆/finish 工具，共享必然重名报错。
        self.researcher = create_research_agent(
            toolkit=self.tool_pool.new_toolkit(),
            long_term_memory=self.long_term_memory,
        )
        self.reviewer = create_review_agent(
            toolkit=self.tool_pool.new_toolkit(),
            long_term_memory=self.long_term_memory,
        )

        # ── 调度层: Leader ──
        toolkit: Toolkit = self.tool_pool.new_toolkit()

        async def invoke_researcher(requirement: str) -> ToolResponse:
            """调用研究助手搜集资料。

            Args:
                requirement: 搜集需求描述
            """
            result = await self.researcher(
                Msg(name="leader", content=requirement, role="user")
            )
            return ToolResponse(
                content=[TextBlock(type="text", text=result.get_text_content() or "")]
            )

        async def invoke_reviewer(content: str) -> ToolResponse:
            """调用审查 Agent 检查质量。

            Args:
                content: 待审查的内容
            """
            result = await self.reviewer(
                Msg(name="leader", content=f"请审查:\n{content}", role="user")
            )
            return ToolResponse(
                content=[TextBlock(type="text", text=result.get_text_content() or "")]
            )

        toolkit.register_tool_function(invoke_researcher)
        toolkit.register_tool_function(invoke_reviewer)

        self.leader = create_react_agent(
            name="Project Leader",
            sys_prompt=LEADER_PROMPT,
            toolkit=toolkit,
            long_term_memory=self.long_term_memory,
            # 规划能力: 8 个计划工具会注册进上面的 toolkit
            plan_notebook=PlanNotebook(),
        )

        # ── 会话（任务）历史回放 ──
        # 重新打开一个任务时，把最近的对话灌回 Leader 的记忆，
        # 这样它是「接着聊」，而不是从零开始。
        if session_id:
            await asyncio.to_thread(ensure_session, user_id, session_id)
            history = await asyncio.to_thread(
                recent_turns, user_id, session_id, HISTORY_REPLAY_TURNS
            )
            if history:
                await self.leader.memory.add(
                    [
                        Msg(
                            name=m["name"] or m["role"],
                            content=m["content"],
                            role=m["role"],
                        )
                        for m in history
                    ]
                )
                logger.info(
                    "任务 %s…/%s: 回放 %d 条历史消息",
                    user_id[:8], session_id, len(history),
                )

    def enable_streaming(self, queue: asyncio.Queue) -> None:
        """把全队的输出接入同一个消息队列，供接入层做流式转发。

        agentscope 的 Agent 在每次 print() 时会把消息副本放进 msg_queue
        （流式分片 last=False，最后一条 last=True）。三个 Agent 共用同一个
        队列，接入层即可按到达顺序实时转发。

        Args:
            queue: 调用方提供的队列。容量由调用方决定 —— 不设上限可避免
                消费不及时时 Agent 阻塞在 put() 上。
        """
        for agent in (self.leader, self.researcher, self.reviewer):
            agent.set_msg_queue_enabled(True, queue=queue)

    def disable_streaming(self) -> None:
        """关闭流式输出，恢复仅控制台输出的默认行为。"""
        for agent in (self.leader, self.researcher, self.reviewer):
            agent.set_msg_queue_enabled(False)

    async def chat(self, user_request: str) -> str:
        """处理用户请求 (保留上下文)。

        Args:
            user_request: 用户请求

        Returns:
            Leader 的最终回复
        """
        msg = Msg(name="user", content=user_request, role="user")
        response = await self.leader(msg)
        reply = response.get_text_content() or ""
        # 写入该任务的会话历史：UI 的分页浏览、下次打开时的回放都读它
        if self.session_id:
            await asyncio.to_thread(
                append_turn, self.user_id, self.session_id, user_request, reply
            )
        return reply


async def run_hierarchical(
    user_request: str, session_id: str = "", user_id: str = "local"
) -> str:
    """便捷函数: 单次层级协作调用。

    Args:
        user_request: 用户请求
        session_id: 会话（任务）ID
        user_id: 用户 ID（多用户隔离的根本）

    Returns:
        Leader 回复
    """
    team = await HierarchicalTeam.create(session_id=session_id, user_id=user_id)
    return await team.chat(user_request)
