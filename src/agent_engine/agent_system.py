"""
Agent 智能体系统
将工具、记忆、规划、协作、技能等所有能力整合为一个统一的智能体
"""
import asyncio
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.message import Msg
from agentscope.memory import InMemoryMemory
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter

from src.config import DASHSCOPE_API_KEY, LLM_MODEL, MAX_REACT_ITERS
from src.tools.tool_manager import register_mcp_tools, register_skill_tools, close_mcp_client
from src.memory.long_term import create_long_term_memory, create_agent_with_ltm
from src.skills.skill_loader import SkillManager


class AgentSystem:
    """统一的智能体系统。

    将所有能力整合为一个 Agent:
    - 工具调用 (MCP + Skill + 动态工具)
    - 记忆管理 (短期 + 长期)
    - 规划执行 (PlanNotebook)
    - 多 Agent 协作 (Hierarchical + Co-creation)
    - Skill 系统 (本地 + 社区)
    """

    def __init__(
        self,
        name: str = "Teaching Assistant",
        sys_prompt: str = None,
        enable_memory: bool = True,
        enable_planning: bool = True,
        enable_skills: bool = True,
        enable_mcp: bool = True,
    ):
        """初始化 Agent 系统。

        Args:
            name: Agent 名称
            sys_prompt: 系统提示词，默认包含所有能力描述
            enable_memory: 是否启用长期记忆
            enable_planning: 是否启用规划能力
            enable_skills: 是否启用 Skill 系统
            enable_mcp: 是否启用 MCP 工具
        """
        self.name = name
        self.enabled_features = {
            "memory": enable_memory,
            "planning": enable_planning,
            "skills": enable_skills,
            "mcp": enable_mcp,
        }

        # 构建系统提示词 (包含所有已启用能力)
        self.sys_prompt = sys_prompt or self._build_sys_prompt()

        # 初始化组件
        self.toolkit = Toolkit()
        self.mcp_client = None
        self.long_term_memory = None
        self.skill_manager = SkillManager()
        self.agent = None

    def _build_sys_prompt(self) -> str:
        """构建包含所有能力的系统提示词。"""
        parts = [f"你是一个智能教学助手 ({self.name})。"]

        features = []
        if self.enabled_features["mcp"]:
            features.append("- 你可以使用 MCP 工具搜索互联网和学术论文")
        if self.enabled_features["skills"]:
            features.append("- 你拥有 Skill 系统，可以按需加载专业审查流程")
        if self.enabled_features["planning"]:
            features.append("- 面对复杂任务时，你会先创建计划，然后逐步执行")
        if self.enabled_features["memory"]:
            features.append("- 你会记住重要的偏好和经验，跨会话保持连贯")

        if features:
            parts.append("你的能力:")
            parts.extend(features)

        parts.append(
            "\n请根据用户需求，灵活使用上述能力来解决问题。"
        )

        return "\n".join(parts)

    async def initialize(self):
        """初始化所有组件 (异步)"""
        # 1. 注册 MCP 工具
        if self.enabled_features["mcp"]:
            self.mcp_client = await register_mcp_tools(self.toolkit)

        # 2. 注册 Skill
        if self.enabled_features["skills"]:
            registered = register_skill_tools(self.toolkit)
            if registered:
                print(f"  已注册 Skill: {', '.join(registered)}")

        # 3. 初始化长期记忆
        if self.enabled_features["memory"]:
            self.long_term_memory = create_long_term_memory(enabled=True)

        # 4. 创建 Agent
        self.agent = ReActAgent(
            name=self.name,
            sys_prompt=self.sys_prompt,
            model=DashScopeChatModel(
                model_name=LLM_MODEL,
                api_key=DASHSCOPE_API_KEY,
            ),
            formatter=DashScopeChatFormatter(),
            toolkit=self.toolkit,
            memory=InMemoryMemory(),
            max_iters=MAX_REACT_ITERS,
            long_term_memory=self.long_term_memory,
            long_term_memory_mode="agent_control" if self.enabled_features["memory"] else None,
        )

    async def chat(self, message: str) -> str:
        """与 Agent 对话 (保留上下文)。

        Args:
            message: 用户消息

        Returns:
            Agent 回复
        """
        if self.agent is None:
            await self.initialize()

        msg = Msg(name="user", content=message, role="user")
        response = await self.agent(msg)
        return response.content

    async def close(self):
        """关闭资源。"""
        if self.mcp_client:
            await close_mcp_client(self.mcp_client)


# ── 便捷函数 ──

async def create_agent_system(**kwargs) -> AgentSystem:
    """创建并初始化 Agent 系统。

    Returns:
        已初始化的 AgentSystem 实例
    """
    system = AgentSystem(**kwargs)
    await system.initialize()
    return system


async def run_agent_system(message: str, **kwargs) -> str:
    """单次提问。

    Args:
        message: 用户问题

    Returns:
        Agent 回复
    """
    system = AgentSystem(**kwargs)
    try:
        await system.initialize()
        return await system.chat(message)
    finally:
        await system.close()
