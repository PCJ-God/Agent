"""
圆桌共创模式 (Co-creation)
多个 Agent 通过 MsgHub 共享消息，多轮迭代讨论
"""
import asyncio
from agentscope.agent import ReActAgent
from agentscope.message import Msg
from agentscope.pipeline import MsgHub
from agentscope.tool import Toolkit
from agentscope.formatter import DashScopeChatFormatter

from src.agent_engine.agent_factory import (
    create_research_agent,
    create_review_agent,
    create_planning_agent,
)


class CoCreationTeam:
    """圆桌共创团队，保持 Agent 状态跨多轮对话。"""

    def __init__(self, num_rounds: int = 2):
        self.num_rounds = num_rounds
        # 创建参与者 (持久化实例，保留对话历史)
        self.researcher = create_research_agent()
        self.reviewer = create_review_agent()
        self.planner = create_planning_agent()
        self.participants = [self.researcher, self.reviewer, self.planner]

        # 秘书 Agent (持久化)
        self.secretary = ReActAgent(
            name="Secretary",
            sys_prompt=(
                "你是一个秘书，负责将以上讨论内容汇总为一份简洁的会议纪要。\n"
                "包括: 各方观点、共识点、分歧点、下一步行动。"
            ),
            model=create_research_agent().model,
            toolkit=Toolkit(),
            formatter=DashScopeChatFormatter(),
        )

    async def discuss(self, user_request: str) -> str:
        """进行一轮圆桌讨论并获取总结 (保留上下文)。

        Args:
            user_request: 讨论主题

        Returns:
            秘书的总结内容
        """
        # 开始圆桌讨论
        async with MsgHub(
            participants=self.participants,
            announcement=Msg(
                'system',
                f"我们要讨论以下问题:\n{user_request}\n"
                f"请每人发表意见，共进行 {self.num_rounds} 轮讨论。",
                "system",
            )
        ):
            for round_idx in range(self.num_rounds):
                for agent in self.participants:
                    prompt = f"请发表你的第 {round_idx + 1} 轮意见。"
                    await agent(Msg(name="host", content=prompt, role="user"))

        # 讨论结束，秘书汇总
        summary = await self.secretary(
            Msg(name="host", content="请根据以上讨论，生成会议纪要。", role="user")
        )

        return summary.content


async def run_cocreation(user_request: str, num_rounds: int = 2) -> str:
    """运行圆桌共创模式 (单次调用，向后兼容)。

    多个 Agent 围坐在"圆桌"旁，通过 MsgHub 共享消息枢纽。
    每个 Agent 的发言都会被其他所有 Agent "听到"。

    Args:
        user_request: 用户请求
        num_rounds: 讨论轮数

    Returns:
        秘书 Agent 的总结
    """
    team = CoCreationTeam(num_rounds=num_rounds)
    return await team.discuss(user_request)
