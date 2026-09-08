#!/usr/bin/env python
"""
运行自动化评测
"""
import sys
import json
import argparse
import asyncio
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import check_api_key
from src.evaluation.evaluator import AgentEvaluator


def main():
    parser = argparse.ArgumentParser(description="Agent 自动化评测")
    parser.add_argument("--all", action="store_true", help="运行全部评测用例")

    args = parser.parse_args()

    # 检查 API Key
    try:
        check_api_key()
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)

    # 运行评测
    evaluator = AgentEvaluator()

    if not evaluator.eval_cases:
        print("没有评测用例，请先在 data/eval_cases.json 中添加。")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"开始评测，共 {len(evaluator.eval_cases)} 个用例")
    print(f"{'='*60}\n")

    results = asyncio.run(evaluator.run_eval())

    # 输出结果
    print(f"\n{'='*60}")
    print("评测结果")
    print(f"{'='*60}")
    print(f"用例总数: {results['total_cases']}")
    print(f"平均得分: {results['average_score']:.2f}\n")

    print(f"{'用例ID':<15} {'得分':<8} {'回复预览'}")
    print("-" * 60)
    for r in results["results"]:
        print(f"{r['case_id']:<15} {r['score']:<8} {r.get('response_preview', '')[:40]}")

    # 保存结果
    output_path = Path(__file__).parent.parent / "data" / "eval_result.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
