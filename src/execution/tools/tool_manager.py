"""
工具管理模块
负责远程 MCP 工具的连接、Skill 的发现，以及两者的池化与分发
"""
import logging
from pathlib import Path

from agentscope.mcp import HttpStatelessClient
from agentscope.tool import Toolkit

from src.config import DASHSCOPE_API_KEY, MCP_SERVER_URL, SKILLS_DIR

logger = logging.getLogger(__name__)


async def create_mcp_client() -> HttpStatelessClient | None:
    """建立远程 MCP 客户端。

    `HttpStatelessClient` 是无状态的 —— 不需要 `connect()`，每次调用各自建连，
    也没有需要在退出时释放的连接（agent 侧的查询见 _toolkit.py:1096-1103，
    那里只对 stateful 客户端校验 is_connected）。

    失败返回 None，让上层降级为「没有 MCP 工具」，而不是启动失败。

    Returns:
        MCP 客户端实例；失败返回 None
    """
    try:
        return HttpStatelessClient(
            name="web_search_service",
            transport="streamable_http",
            url=MCP_SERVER_URL,
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
        )
    except Exception as e:
        logger.warning("远程 MCP 连接失败: %s，将降级为无 MCP 工具", e)
        return None


def list_skill_dirs(skills_dir: str = "") -> list[str]:
    """列出所有 Skill 目录（顶层含 SKILL.md 的那些）。

    agentscope 的 `register_agent_skill()` 一次只接受**一个** Skill 目录
    （见 _toolkit.py:1323-1348），所以需要自己枚举子目录。

    Args:
        skills_dir: Skill 根目录，默认取配置 SKILLS_DIR

    Returns:
        Skill 目录路径列表
    """
    root = Path(skills_dir) if skills_dir else SKILLS_DIR
    return [str(p.parent) for p in sorted(root.glob("*/SKILL.md"))]


class ToolPool:
    """团队共享的工具池。

    工具的「来源」只有一份 —— MCP 工具在这里抓取一次、Skill 在这里枚举一次 ——
    然后由 `new_toolkit()` 按 Agent 分发。

    **为什么分发 Toolkit，而不是让所有 Agent 共享同一个？**
    因为 Toolkit 是 Agent 的**可变状态**，不是只读配置：ReActAgent 在构造期会往
    里注册 plan 工具 (_react_agent.py:339-348) 和 agent_control 记忆工具
    (:301-308)，运行期还会注册/移除 finish_function (:413/:426)。而
    `register_tool_function` 遇到重名默认直接抛错，实测：

        两个 Agent 共用一个 Toolkit
        -> ValueError: A function with name 'view_subtasks' is already
           registered in the toolkit.

    **反过来，工具函数对象本身可以安全共享** —— 同一批函数对象注册进不同的
    Toolkit 互不影响（`get_callable_function()` 返回的 MCPToolFunction 只持有
    MCP 工具 schema 与 client 生成器，不绑定 toolkit），实测两个 Agent 各 9 个
    工具、都正常。这正是"池化"的立足点。
    """

    def __init__(
        self,
        mcp_functions: list | None = None,
        tool_names: list[str] | None = None,
        skill_dirs: list[str] | None = None,
    ) -> None:
        self.tool_names = list(tool_names or [])
        self.skill_dirs = list(skill_dirs or [])
        self._mcp_functions = list(mcp_functions or [])

    @classmethod
    async def create(
        cls,
        mcp_client: HttpStatelessClient | None = None,
        skills_dir: str = "",
    ) -> "ToolPool":
        """抓取一次工具，形成池。

        Args:
            mcp_client: 已建立的 MCP 客户端；None 表示池里只有 Skill
            skills_dir: Skill 根目录，默认取配置

        Returns:
            就绪的 ToolPool
        """
        mcp_functions: list = []
        tool_names: list[str] = []

        if mcp_client is not None:
            # 与 Toolkit.register_mcp_client 内部同样的两步
            # (agentscope/tool/_toolkit.py:1138-1154)：列出工具 → 取可调用对象。
            # 这样只需抓一次，后续每个 Agent 复用同一批函数对象。
            for mcp_tool in await mcp_client.list_tools():
                tool_names.append(mcp_tool.name)
                mcp_functions.append(
                    await mcp_client.get_callable_function(
                        func_name=mcp_tool.name,
                        wrap_tool_result=True,
                    )
                )

        skill_dirs = list_skill_dirs(skills_dir)

        logger.info(
            "工具池就绪: MCP 工具 %d 个%s | Skill %d 个%s",
            len(tool_names),
            f" ({', '.join(tool_names)})" if tool_names else "",
            len(skill_dirs),
            f" ({', '.join(Path(d).name for d in skill_dirs)})" if skill_dirs else "",
        )

        return cls(mcp_functions, tool_names, skill_dirs)

    def new_toolkit(self) -> Toolkit:
        """从池里复制出一份新的 Toolkit，交给一个 Agent 独占使用。

        Returns:
            装配好池内全部 MCP 工具与 Skill 的新 Toolkit
        """
        toolkit = Toolkit()

        for func in self._mcp_functions:
            toolkit.register_tool_function(func)

        for skill_dir in self.skill_dirs:
            toolkit.register_agent_skill(skill_dir)

        return toolkit
