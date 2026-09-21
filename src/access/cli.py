"""
接入层 - CLI 入口
处理用户命令行输入，传递给调度层
"""
import sys
import asyncio
from collections.abc import Awaitable

# 从子模块导入: dashscope/__init__.pyi 把这个函数错误地声明成了同步函数，
# 会让 Pylance 误报 "None 并非 awaitable"。
from dashscope.api_entities.aio_session import close_shared_aio_session

from src.config import check_api_key, setup_logging
from src.orchestration.hierarchical import HierarchicalTeam, run_hierarchical


async def _chat_with_cleanup(awaitable: Awaitable[str]) -> str:
    """执行一次对话，并在退出前释放 dashscope 的连接池。

    dashscope 会为每个事件循环缓存一个 aiohttp ClientSession，
    若在 loop 关闭前不释放，解释器退出时会打印
    'Unclosed client session' / 'Event loop is closed' 等告警。
    """
    try:
        return await awaitable
    finally:
        await close_shared_aio_session()


async def run_interactive(session_id: str = "cli-default", user_id: str = "local") -> None:
    """交互式多轮对话 (Hierarchical 模式)。

    整个会话共用一个事件循环：Agent、MCP 连接、向量库客户端都持有
    循环内的资源，若沿用"每轮 asyncio.run 一个新循环"的写法，
    跨循环复用这些对象会出问题。
    """
    print("=" * 60)
    print("Agent 智能教学助手 — 层级协作模式 (Hierarchical)")
    print("架构: 接入层 → 调度层(Leader) → 执行层(Researcher + Reviewer)")
    print("输入 'quit' 或 'exit' 退出")
    print(f"用户 ID: {user_id}   任务 ID: {session_id}")
    print("(--user / --session 可切换；不同用户、不同任务之间记忆互不可见)")
    print("=" * 60)

    team = await HierarchicalTeam.create(session_id=session_id, user_id=user_id)

    try:
        while True:
            try:
                question = (await asyncio.to_thread(input, "\n> 你的问题: ")).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见!")
                break

            if not question or question.lower() in ("quit", "exit"):
                print("再见!")
                break

            try:
                print(f"\n回复:\n{await team.chat(question)}")
            except Exception as e:
                print(f"\n错误: {e}")
    finally:
        await close_shared_aio_session()


async def run_single_question(
    question: str, session_id: str = "cli-default", user_id: str = "local"
) -> str:
    """单次提问。"""
    return await _chat_with_cleanup(
        run_hierarchical(question, session_id=session_id, user_id=user_id)
    )


def main():
    """CLI 主入口。"""
    import argparse

    setup_logging()

    parser = argparse.ArgumentParser(description="Agent 智能教学助手 — 层级协作模式")
    parser.add_argument("--question", "-q", type=str, help="直接提问")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument(
        "--session",
        "-s",
        type=str,
        default="cli-default",
        help="任务 ID。不同任务的记忆互相隔离；复用同一 ID 可持续累积长期记忆",
    )
    parser.add_argument(
        "--user",
        "-u",
        type=str,
        default="local",
        help="用户 ID。不同用户的记忆与会话完全隔离（CLI 单机场景默认 local）",
    )

    args = parser.parse_args()

    try:
        check_api_key()
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)

    if args.question:
        print(f"\n问题: {args.question}\n")
        response = asyncio.run(
            run_single_question(args.question, args.session, args.user)
        )
        print(f"\n回复:\n{response}")
    else:
        asyncio.run(run_interactive(args.session, args.user))


if __name__ == "__main__":
    main()
