#!/usr/bin/env python
"""
运行 Agent CLI 脚本
支持多种 Agent 模式和直接提问

工具来源:
1. MCP 工具 (连接远端 MCP Server)
2. Skill (SKILL.md 定义的标准化流程)
3. 动态工具注册 (Agent 运行时通过代码解释器创建)
"""
import sys
import argparse
import asyncio
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import check_api_key
from src.tools.tool_manager import register_mcp_tools, register_skill_tools, close_mcp_client
from src.agent_engine.react_agent import create_react_agent, run_agent_query
from src.orchestration.hierarchical import run_hierarchical, HierarchicalTeam
from src.orchestration.cocreation import run_cocreation, CoCreationTeam
from agentscope.tool import Toolkit


async def setup_toolkit():
    """设置 Toolkit，注册 MCP 工具和 Skill。

    Returns:
        (toolkit, mcp_client) 元组
    """
    toolkit = Toolkit()

    # 1. 注册 MCP 工具
    mcp_client = await register_mcp_tools(toolkit)

    # 2. 注册 Skill 工具
    registered_skills = register_skill_tools(toolkit)
    if registered_skills:
        print(f"已注册 Skill: {', '.join(registered_skills)}")

    return toolkit, mcp_client


def run_interactive_react():
    """ReAct 多轮对话: 共享 toolkit 和 agent 实例，保留上下文记忆。"""
    print("=" * 60)
    print("Agent 智能教学助手 (ReAct 多轮对话)")
    print("工具来源: MCP 工具 + Skill + 动态工具注册")
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 60)

    # 设置工具包 (MCP + Skill)
    toolkit, mcp_client = asyncio.run(setup_toolkit())

    # 创建一次 Agent，复用实例 (保留对话历史)
    from agentscope.message import Msg

    agent = create_react_agent(toolkit=toolkit)

    try:
        while True:
            try:
                question = input("\n> 你的问题: ").strip()
                if not question or question.lower() in ("quit", "exit"):
                    print("再见!")
                    break

                msg = Msg(name="user", content=question, role="user")
                response = asyncio.run(agent(msg))
                print(f"\n回复:\n{response.content}")

            except KeyboardInterrupt:
                print("\n再见!")
                break
            except Exception as e:
                print(f"\n错误: {e}")
    finally:
        asyncio.run(close_mcp_client(mcp_client))


def run_interactive_hierarchical():
    """Hierarchical 多轮交互模式 (复用 HierarchicalTeam，保留上下文)。"""
    print("=" * 60)
    print("Agent 智能教学助手 (Hierarchical 层级协作)")
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 60)

    team = HierarchicalTeam()  # 创建一次，复用所有对话

    while True:
        try:
            question = input("\n> 你的问题: ").strip()
            if not question or question.lower() in ("quit", "exit"):
                print("再见!")
                break

            response = asyncio.run(team.chat(question))
            print(f"\n回复:\n{response}")

        except KeyboardInterrupt:
            print("\n再见!")
            break
        except Exception as e:
            print(f"\n错误: {e}")


def run_interactive_cocreation():
    """Co-creation 多轮交互模式 (复用 CoCreationTeam，保留上下文)。"""
    print("=" * 60)
    print("Agent 智能教学助手 (Co-creation 圆桌共创)")
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 60)

    team = CoCreationTeam()  # 创建一次，复用所有对话

    while True:
        try:
            question = input("\n> 你的问题: ").strip()
            if not question or question.lower() in ("quit", "exit"):
                print("再见!")
                break

            response = asyncio.run(team.discuss(question))
            print(f"\n回复:\n{response}")

        except KeyboardInterrupt:
            print("\n再见!")
            break
        except Exception as e:
            print(f"\n错误: {e}")


async def run_single_question(question: str, mode: str):
    """单次提问。

    Args:
        question: 用户问题
        mode: Agent 模式
    """
    if mode == "react":
        toolkit, mcp_client = await setup_toolkit()
        try:
            register_skill_tools(toolkit)
            response = await run_agent_query(question, toolkit=toolkit)
        finally:
            await close_mcp_client(mcp_client)
        return response

    elif mode == "hierarchical":
        return await run_hierarchical(question)

    elif mode == "cocreation":
        return await run_cocreation(question)


def main():
    parser = argparse.ArgumentParser(description="Agent 智能教学助手 CLI")
    parser.add_argument("--question", "-q", type=str, help="直接提问")
    parser.add_argument("--mode", "-m", type=str, default="react",
                        choices=["react", "hierarchical", "cocreation"],
                        help="Agent 模式 (默认: react)")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="交互模式")

    args = parser.parse_args()

    # 检查 API Key
    try:
        check_api_key()
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)

    if args.question:
        # 直接提问
        print(f"\n问题: {args.question}")
        print(f"模式: {args.mode}\n")

        response = asyncio.run(run_single_question(args.question, args.mode))
        print(f"\n回复:\n{response}")

    elif args.interactive:
        # 交互模式 (根据选择的模式启动)
        if args.mode == "react":
            run_interactive_react()
        elif args.mode == "hierarchical":
            run_interactive_hierarchical()
        elif args.mode == "cocreation":
            run_interactive_cocreation()

    else:
        # 默认进入交互模式 (不传 --question 时直接进入多轮对话)
        if args.mode == "react":
            run_interactive_react()
        elif args.mode == "hierarchical":
            run_interactive_hierarchical()
        elif args.mode == "cocreation":
            run_interactive_cocreation()


if __name__ == "__main__":
    main()
