"""
自动化评测模块
支持端到端和白盒化评测
"""
import json
from pathlib import Path
from agentscope.message import Msg

from src.config import DATA_DIR
from src.agent_engine.react_agent import create_react_agent, run_agent_query
from src.tools.tool_manager import register_default_tools
from agentscope.tool import Toolkit


class AgentEvaluator:
    """Agent 评测器。

    从 eval_cases.json 加载评测用例，运行 Agent 并评分。
    """

    def __init__(self, eval_cases_path: str = None):
        """初始化评测器。

        Args:
            eval_cases_path: 评测用例文件路径
        """
        self.eval_cases_path = Path(eval_cases_path) if eval_cases_path else DATA_DIR / "eval_cases.json"
        self.eval_cases = self._load_cases()

    def _load_cases(self) -> list:
        """加载评测用例。

        Returns:
            评测用例列表
        """
        if not self.eval_cases_path.exists():
            print(f"评测用例文件不存在: {self.eval_cases_path}")
            return []

        with open(self.eval_cases_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def run_eval(self) -> dict:
        """运行评测。

        Returns:
            评测结果字典
        """
        if not self.eval_cases:
            return {"error": "没有评测用例"}

        results = []
        total_score = 0

        for case in self.eval_cases:
            result = await self._eval_case(case)
            results.append(result)
            total_score += result.get("score", 0)

        avg_score = total_score / len(results) if results else 0

        return {
            "total_cases": len(results),
            "average_score": round(avg_score, 2),
            "results": results,
        }

    async def _eval_case(self, case: dict) -> dict:
        """评测单个用例。

        Args:
            case: 评测用例

        Returns:
            评测结果
        """
        question = case.get("question", "")
        expected_tools = case.get("expected_tools", [])

        # 运行 Agent
        toolkit = Toolkit()
        register_default_tools(toolkit)

        try:
            response = await run_agent_query(question, toolkit=toolkit)

            # 提取文本内容 (response 是 [{"type": "text", "text": "..."}])
            if isinstance(response, list):
                response_text = ""
                for block in response:
                    if isinstance(block, dict) and block.get("type") == "text":
                        response_text += block.get("text", "")
            else:
                response_text = str(response)

            # 评分逻辑
            score = 0

            # 1. 回复长度分: 回复非空且有一定长度
            if response_text and len(response_text) > 10:
                score += 1

            # 2. 工具调用分: 是否调用了期望的工具
            if expected_tools:
                tools_mentioned = sum(1 for t in expected_tools if t in response_text)
                score += tools_mentioned / len(expected_tools)

            return {
                "case_id": case.get("id", ""),
                "question": question,
                "score": round(score, 2),
                "response_preview": response_text[:100] if response_text else "",
                "response_length": len(response_text),
                "tools_used": [t for t in expected_tools if t in response_text],
            }

        except Exception as e:
            return {
                "case_id": case.get("id", ""),
                "question": question,
                "score": 0,
                "error": str(e),
            }
