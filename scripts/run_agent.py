#!/usr/bin/env python
"""
运行 Agent CLI 脚本
支持多种 Agent 模式和直接提问
"""
import sys
import argparse
import asyncio
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import check_api_key
from src.tools.tool_manager import register_default_tools
from src.agent_engine.react_agent import run_agent_query
from src.orchestration.hierarchical import run_hierarchical
from src.orchestration.cocreation import run_cocreation
from agentscope.tool import Toolkit


def run_interactive_react():
    """ReAct 多轮对话: 共享 toolkit 和 agent 实例，保留上下文记忆。"""
    print("=" * 60)
    print("Agent 智能教学助手 (ReAct 多轮对话)")
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 60)

    toolkit = Toolkit()
    register_default_tools(toolkit)

    # 创建一次 Agent，复用实例 (保留对话历史)
    from src.agent_engine.react_agent import create_react_agent
    from agentscope.message import Msg

    agent = create_react_agent(toolkit=toolkit)

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


def run_interactive_hierarchical():
    """Hierarchical 多轮交互模式 (复用 HierarchicalTeam，保留上下文)。"""
    from src.orchestration.hierarchical import HierarchicalTeam

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
    from src.orchestration.cocreation import CoCreationTeam

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

        if args.mode == "react":
            toolkit = Toolkit()
            register_default_tools(toolkit)
            response = asyncio.run(run_agent_query(args.question, toolkit=toolkit))
        elif args.mode == "hierarchical":
            response = asyncio.run(run_hierarchical(args.question))
        elif args.mode == "cocreation":
            response = asyncio.run(run_cocreation(args.question))

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
