"""
工具管理模块
负责远程 MCP 工具的连接、Skill 的发现，以及两者的池化与分发
"""
import logging
from pathlib import Path
from urllib.parse import urlparse

from agentscope.mcp import HttpStatelessClient
from agentscope.tool import Toolkit

from src.config import DASHSCOPE_API_KEY, MCP_SERVER_URL, SKILLS_DIR
from src.execution.tools.skill_files import (
    SKILL_INSTRUCTION,
    SKILL_TEMPLATE,
    frontmatter_name,
    make_skill_reader,
)

logger = logging.getLogger(__name__)

# 远程 MCP 服务的名字。定义在这里而不是写在 create_mcp_client 里面，
# 是因为界面上要展示它 —— 两处各写一份字面量迟早会对不上。
MCP_SERVICE_NAME = "web_search_service"


def mcp_server_info() -> dict:
    """MCP 服务的展示信息。

    **只给主机名，不给完整 URL，更不给 header** —— header 里是 DASHSCOPE_API_KEY，
    这个字典会经由 /api/mcp 返回给浏览器。
    """
    return {
        "name": MCP_SERVICE_NAME,
        "transport": "streamable_http",
        "host": urlparse(MCP_SERVER_URL).hostname or "",
    }


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
            name=MCP_SERVICE_NAME,
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


def _merge_skill_dirs(builtin: list[str], extra: list[str]) -> list[str]:
    """内置技能优先；用户技能重名就跳过并记一条日志。

    重名必须在这里拦掉：agentscope 的 `register_agent_skill()` 遇到重名直接抛
    ValueError（见 _toolkit.py:1381-1384），一旦抛出去**整个团队都装配不起来** ——
    用户只是取了个和内置技能一样的名字，不该让他的会话彻底不可用。
    """
    seen = {frontmatter_name(Path(d)) for d in builtin}
    merged = list(builtin)
    for d in extra:
        name = frontmatter_name(Path(d))
        if name in seen:
            logger.warning("技能 '%s' 与已有技能重名，已跳过: %s", name, d)
            continue
        seen.add(name)
        merged.append(d)
    return merged


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
        extra_skill_dirs: list[str] | None = None,
    ) -> "ToolPool":
        """抓取一次工具，形成池。

        Args:
            mcp_client: 已建立的 MCP 客户端；None 表示池里只有 Skill
            skills_dir: 内置 Skill 根目录，默认取配置
            extra_skill_dirs: 额外的技能目录（用户自建技能的物化目录）

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

        skill_dirs = _merge_skill_dirs(
            list_skill_dirs(skills_dir), list(extra_skill_dirs or [])
        )

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

        除了池里的 MCP 工具与 Skill，还挂一个**受限的技能读取器**：技能清单里
        只给名字和描述，正文要靠它按需去取（原因见 `skill_files` 模块头部）。
        框架默认的技能模板只说 `Check "{dir}/SKILL.md"` —— 既没点名工具（Agent
        手上没有读文件的工具，技能就一直空转），又把服务器绝对路径交给了远程
        LLM，所以这里用 SKILL_TEMPLATE / SKILL_INSTRUCTION 覆盖掉。

        Returns:
            装配好池内全部 MCP 工具、Skill 与技能读取器的新 Toolkit
        """
        toolkit = Toolkit(
            agent_skill_instruction=SKILL_INSTRUCTION,
            agent_skill_template=SKILL_TEMPLATE,
        )

        for func in self._mcp_functions:
            toolkit.register_tool_function(func)

        for skill_dir in self.skill_dirs:
            toolkit.register_agent_skill(skill_dir)

        # 一个技能都没有时不挂：挂一个必然回「没有这个技能」的工具没有意义
        if self.skill_dirs:
            toolkit.register_tool_function(make_skill_reader(self.skill_dirs))

        return toolkit
