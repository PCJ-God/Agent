#!/usr/bin/env python
"""
运行规划与执行演示
展示课程 3.2 中的所有规划能力
"""
import sys
import argparse
import asyncio
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import check_api_key
from src.planning.reflection import self_review_mode, external_feedback_mode
from src.planning.workflow import (
    run_pipeline_workflow,
    run_branching_workflow,
    run_parallel_workflow,
    run_moa_workflow,
    run_hitl_workflow,
)
from src.planning.plan_notebook import run_planning_workflow
from src.planning.dynamic_tools import run_dynamic_tool_creation


def print_section(title: str):
    """打印分隔线和标题。"""
    print(f"\n{'='*60}")
    print(f"📋 {title}")
    print(f"{'='*60}\n")


async def run_all_demos():
    """运行所有规划能力演示。"""
    # 检查 API Key
    try:
        check_api_key()
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)

    # 1. 反思模式 - 自我反馈
    print_section("反思模式 1: 自我反馈 (Self-Review)")
    original = "def hello():\n    print('world')"
    draft = "def hello():\n    print('World!')"
    result = await self_review_mode(original, draft)
    print(f"审查结果:\n{result}")

    # 2. 反思模式 - 外部反馈
    print_section("反思模式 2: 外部反馈 (External Feedback)")
    course_code = """
def get_user_data(usr_id: str):
    return f"Data for {usr_id}"

print(get_user_data(usr_id="u-123"))
"""
    result = await external_feedback_mode(course_code)
    print(f"Agent 输出:\n{result[:500]}...")

    # 3. 流水线工作流
    print_section("工作流 1: 流水线 (Pipeline)")
    content = "这是新课程。第一部分: print('Hello')。第二部分: x = 1/0。"
    result = await run_pipeline_workflow(content)
    print(f"流水线输出:\n{result[:500]}...")

    # 4. 分支工作流
    print_section("工作流 2: 分支选择 (Branching)")
    request = "这篇课程写的差不多了，帮我全面检查一下，特别是代码和难度。"
    result = await run_branching_workflow(request)
    print(f"分支输出:\n{result[:500]}...")

    # 5. 并行工作流
    print_section("工作流 3: 并行执行 (Parallel)")
    content = "这是我们新开发的 Python 数据分析入门课..."
    result = await run_parallel_workflow(content)
    print(f"并行输出:\n{result[:500]}...")

    # 6. MoA 工作流
    print_section("工作流 4: 混合专家 (MoA)")
    task = "为新的'面向 Web 开发者的 AI 大模型应用'课程提炼核心卖点和宣传文案。"
    result = await run_moa_workflow(task)
    print(f"MoA 输出:\n{result[:500]}...")

    # 7. HITL 工作流
    print_section("工作流 5: 人机协作 (HITL)")
    content = "在 Python 中，装饰器本质上是一个接收函数作为参数并返回一个新函数的函数..."
    # 注意: HITL 需要人工输入，这里跳过自动演示
    print("HITL 需要人工交互，跳过自动演示。")

    # 8. PlanNotebook 自主规划
    print_section("PlanNotebook: 自主规划")
    request = "请帮我完成一门新的 Python 入门课程的前期调研，竞品是 some-site.com 的课程。"
    result = await run_planning_workflow(request)
    print(f"计划状态:\n{result}")

    # 9. 动态工具创建
    print_section("动态工具创建")
    result = await run_dynamic_tool_creation()
    print(f"初始工具: {result['initial_tools']}")
    print(f"最终工具: {result['final_tools']}")
    print(f"新创建工具: {result['new_tools_created']}")


def main():
    parser = argparse.ArgumentParser(description="规划与执行能力演示")
    parser.add_argument("--all", action="store_true", help="运行所有演示")

    args = parser.parse_args()

    if args.all:
        asyncio.run(run_all_demos())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
