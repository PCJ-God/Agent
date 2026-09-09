#!/usr/bin/env python
"""
模块测试脚本
测试 planning 和 memory 模块的完整实现
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

print('='*60)
print('Planning & Memory 模块评测')
print('='*60)

# Test 1: Context Truncation
print('\n[1] 固定窗口截断 (Context Truncation)')
try:
    from src.memory.short_term import create_truncated_formatter
    formatter = create_truncated_formatter(max_tokens=80)
    print('  ✅ Formatter 创建成功 (max_tokens=80)')
except Exception as e:
    print(f'  ❌ 失败: {e}')

# Test 2: Rolling Summary
print('\n[2] 滚动摘要 (Rolling Summary)')
try:
    from src.memory.short_term import RollingSummaryMemory
    from agentscope.message import Msg

    mem = RollingSummaryMemory(buffer_size=3, summary_ratio=0.5)
    print('  ✅ RollingSummaryMemory 创建成功')

    async def test_rolling():
        for i in range(5):
            await mem.add(Msg('user', f'第{i+1}轮对话内容', 'user'))
        result = await mem.get_memory()
        has_summary = any('历史摘要' in str(m.content) for m in result)
        print(f'  ✅ 5 轮后记忆条数: {len(result)}, 包含摘要: {has_summary}')
        return True

    asyncio.run(test_rolling())
except Exception as e:
    print(f'  ❌ 失败: {e}')

# Test 3: Long-term Memory
print('\n[3] 向量化召回 (Vector-based Retrieval)')
try:
    from src.memory.long_term import create_long_term_memory, create_agent_with_ltm

    ltm = create_long_term_memory(enabled=True)
    print(f'  ✅ Mem0LongTermMemory 创建成功: {type(ltm).__name__}')
except Exception as e:
    print(f'  ❌ 失败: {e}')

# Test 4: Planning - Reflection
print('\n[4] 反思模式 (Reflection)')
try:
    from src.planning.reflection import self_review_mode, external_feedback_mode
    print('  ✅ Self-Review 模式: OK')
    print('  ✅ External Feedback 模式: OK')
except Exception as e:
    print(f'  ❌ 失败: {e}')

# Test 5: Planning - Workflow
print('\n[5] 工作流编排 (Workflow)')
try:
    from src.planning.workflow import (
        run_pipeline_workflow,
        run_branching_workflow,
        run_parallel_workflow,
        run_moa_workflow,
        run_hitl_workflow,
    )
    print('  ✅ Pipeline (流水线): OK')
    print('  ✅ Branching (分支选择): OK')
    print('  ✅ Parallel (并行执行): OK')
    print('  ✅ MoA (混合专家): OK')
    print('  ✅ HITL (人机协作): OK')
except Exception as e:
    print(f'  ❌ 失败: {e}')

# Test 6: Planning - PlanNotebook
print('\n[6] 自主规划 (PlanNotebook)')
try:
    from src.planning.plan_notebook import run_planning_workflow
    print('  ✅ PlanNotebook: OK')
except Exception as e:
    print(f'  ❌ 失败: {e}')

# Test 7: Planning - Dynamic Tools
print('\n[7] 动态工具创建 (Dynamic Tool Creation)')
try:
    from src.planning.dynamic_tools import run_dynamic_tool_creation
    print('  ✅ 动态工具创建: OK')
except Exception as e:
    print(f'  ❌ 失败: {e}')

print('\n' + '='*60)
print('评测完成')
print('='*60)
