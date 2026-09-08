# 评测驱动开发模块文档

## 概述

评测驱动开发模块提供了一套**系统化的方法来评估 Agent 系统的性能和质量**。通过端到端评测和白盒化分析,确保 Agent 从"偶尔对"变成"持续对",让好经验固化为可验证的标准。

## 为什么需要评测驱动?

### Agent 开发的挑战

在传统软件开发中,我们有明确的测试用例来验证代码正确性。但 Agent 开发面临以下问题:

1. **非确定性**: 大模型的输出不是确定的,同样的输入可能产生不同的输出
2. **质量主观**: "好"的标准难以量化,不同人有不同判断
3. **流程复杂**: Agent 涉及多个环节(工具调用、规划、执行),难以定位问题
4. **持续退化**: 提示词或工具的微调可能导致某些场景下性能下降

### 评测的价值

```
没有评测:
"这个Agent干得好不好?" → 靠感觉 → 无法持续改进

有评测:
"这个Agent干得好不好?" → 看分数 → 找到短板 → 针对性优化
```

## 评测架构

```
┌──────────────────────────────────────────────────────────┐
│                    评测体系                                │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │            端到端评测 (End-to-End Evaluation)       │ │
│  │  - 完整任务链路的最终输出质量                        │ │
│  │  - 用户视角: 结果是否满足需求                        │ │
│  │  - 黑盒测试: 不关心内部流程                         │ │
│  └─────────────────────────────────────────────────────┘ │
│                          ↕                               │
│  ┌─────────────────────────────────────────────────────┐ │
│  │            白盒化分析 (White-Box Analysis)           │ │
│  │  - 工具调用路径是否正确                             │ │
│  │  - ReAct循环次数是否合理                            │ │
│  │  - 决策质量: 选择了合适的工具吗?                    │ │
│  │  - 错误率: 多少次调用中有多少失败                   │ │
│  └─────────────────────────────────────────────────────┘ │
│                          ↕                               │
│  ┌─────────────────────────────────────────────────────┐ │
│  │            持续改进 (Continuous Improvement)         │ │
│  │  - 基于评测结果迭代优化                             │ │
│  │  - 建立基准线,防止退化                             │ │
│  │  - 发现短板,针对性改进                             │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## 实现方案

### 1. 评测数据集构建

构建有代表性的测试用例集合:

```python
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class EvalCase:
    """评测用例"""
    id: str
    description: str
    user_request: str  # 用户请求
    expected_output: str  # 期望输出 (可选)
    expected_tools: List[str]  # 期望调用的工具 (可选)
    difficulty: str  # 难度: easy, medium, hard
    category: str  # 类别: research, review, summary, etc.

# 构建评测数据集
eval_dataset = [
    EvalCase(
        id="case_001",
        description="搜索特定论文",
        user_request="帮我找到 'Attention Is All You Need' 这篇论文",
        expected_tools=["search_arxiv_paper"],
        difficulty="easy",
        category="research"
    ),
    EvalCase(
        id="case_002",
        description="搜集最新研究进展",
        user_request="搜集 Transformer 模型的最新研究进展",
        expected_tools=["web_search", "search_arxiv_paper"],
        difficulty="medium",
        category="research"
    ),
    EvalCase(
        id="case_003",
        description="复杂任务: 搜集+整理+审查",
        user_request="为我准备一份关于大模型原理的课程文档,并审查质量",
        expected_tools=["web_search", "search_arxiv_paper"],
        difficulty="hard",
        category="comprehensive"
    ),
    # ... 更多用例
]
```

### 2. 端到端评测

从用户角度评估最终输出质量:

```python
class EndToEndEvaluator:
    """端到端评测引擎"""
    
    def __init__(self, agent, eval_dataset):
        self.agent = agent
        self.eval_dataset = eval_dataset
    
    async def run_evaluation(self):
        """运行完整评测"""
        results = []
        
        for case in self.eval_dataset:
            result = await self.evaluate_case(case)
            results.append(result)
        
        # 汇总结果
        report = self.generate_report(results)
        return report
    
    async def evaluate_case(self, case: EvalCase) -> Dict:
        """评测单个用例"""
        
        # 1. 执行任务
        response = await self.agent(
            Msg(name="user", content=case.user_request, role="user")
        )
        
        # 2. 评估输出质量
        quality_score = self.assess_quality(response.content, case)
        
        # 3. 评估工具调用
        tool_calls = self.extract_tool_calls(response)
        tool_score = self.assess_tool_calls(tool_calls, case)
        
        # 4. 评估效率
        efficiency_score = self.assess_efficiency(response)
        
        return {
            "case_id": case.id,
            "description": case.description,
            "quality_score": quality_score,  # 1-5分
            "tool_score": tool_score,        # 1-5分
            "efficiency_score": efficiency_score,  # 1-5分
            "overall_score": (quality_score + tool_score + efficiency_score) / 3,
            "details": {
                "response_length": len(response.content),
                "tool_call_count": len(tool_calls),
                "tools_used": [tc["name"] for tc in tool_calls]
            }
        }
    
    def assess_quality(self, response: str, case: EvalCase) -> float:
        """评估输出质量"""
        # 可以人工评分或使用评判模型
        # 这里使用简单的启发式规则
        
        score = 3.0  # 基准分
        
        # 长度合理
        if 100 < len(response) < 2000:
            score += 0.5
        
        # 包含关键信息
        if case.expected_output:
            keywords = case.expected_output.lower().split()
            match_count = sum(1 for kw in keywords if kw in response.lower())
            match_rate = match_count / len(keywords) if keywords else 0
            score += match_rate * 1.5
        
        return min(5.0, max(1.0, score))
    
    def assess_tool_calls(self, tool_calls: List, case: EvalCase) -> float:
        """评估工具调用"""
        if not case.expected_tools:
            return 3.0  # 没有期望的工具,给基准分
        
        used_tools = [tc["name"] for tc in tool_calls]
        
        # 计算工具匹配率
        expected = set(case.expected_tools)
        actual = set(used_tools)
        
        if expected == actual:
            return 5.0  # 完全匹配
        elif expected.issubset(actual):
            return 4.0  # 包含所有期望工具,但多了几个
        elif expected & actual:  # 有交集
            overlap = len(expected & actual) / len(expected)
            return 2.0 + overlap * 2
        else:
            return 1.0  # 完全不匹配
    
    def assess_efficiency(self, response) -> float:
        """评估执行效率"""
        # 基于工具调用次数和响应长度
        tool_call_count = len(self.extract_tool_calls(response))
        
        if tool_call_count <= 3:
            return 5.0
        elif tool_call_count <= 5:
            return 4.0
        elif tool_call_count <= 10:
            return 3.0
        else:
            return 2.0
    
    def extract_tool_calls(self, response) -> List:
        """从Agent响应中提取工具调用信息"""
        # 从Agent内部状态或日志中提取
        # 这里简化处理
        return []
    
    def generate_report(self, results: List[Dict]) -> str:
        """生成评测报告"""
        total = len(results)
        avg_quality = sum(r["quality_score"] for r in results) / total
        avg_tool = sum(r["tool_score"] for r in results) / total
        avg_efficiency = sum(r["efficiency_score"] for r in results) / total
        avg_overall = sum(r["overall_score"] for r in results) / total
        
        report = f"""
# Agent 评测报告

## 总体指标

| 指标 | 分数 |
|------|------|
| 输出质量 | {avg_quality:.2f}/5.0 |
| 工具调用 | {avg_tool:.2f}/5.0 |
| 执行效率 | {avg_efficiency:.2f}/5.0 |
| 综合评分 | {avg_overall:.2f}/5.0 |

## 详细结果

| 用例 | 描述 | 质量 | 工具 | 效率 | 综合 |
|------|------|------|------|------|------|
"""
        for r in results:
            report += f"| {r['case_id']} | {r['description']} | {r['quality_score']:.1f} | {r['tool_score']:.1f} | {r['efficiency_score']:.1f} | {r['overall_score']:.1f} |\n"
        
        return report
```

### 3. 白盒化分析

深入分析Agent内部执行过程:

```python
class WhiteBoxAnalyzer:
    """白盒化分析引擎"""
    
    def analyze_execution_path(self, agent_trace: Dict) -> Dict:
        """分析Agent的执行路径"""
        
        return {
            "tool_call_path": self.extract_tool_path(agent_trace),
            "react_cycles": self.count_react_cycles(agent_trace),
            "decision_quality": self.assess_decisions(agent_trace),
            "error_rate": self.calculate_error_rate(agent_trace)
        }
    
    def extract_tool_path(self, trace: Dict) -> List[str]:
        """提取工具调用路径"""
        return [step["tool"] for step in trace.get("steps", []) if step.get("tool")]
    
    def count_react_cycles(self, trace: Dict) -> int:
        """计算ReAct循环次数"""
        return len(trace.get("steps", []))
    
    def assess_decisions(self, trace: Dict) -> float:
        """评估决策质量"""
        # 检查每次工具调用是否合理
        good_decisions = 0
        total_decisions = 0
        
        for step in trace.get("steps", []):
            total_decisions += 1
            if step.get("tool") and step.get("result"):
                good_decisions += 1
        
        return good_decisions / total_decisions if total_decisions > 0 else 0
    
    def calculate_error_rate(self, trace: Dict) -> float:
        """计算错误率"""
        errors = sum(1 for step in trace.get("steps", []) if step.get("error"))
        total = len(trace.get("steps", []))
        return errors / total if total > 0 else 0
```

### 4. 评测自动化

```python
async def run_automated_evaluation(agent, dataset_path="tests/eval_cases.json"):
    """自动化评测流程"""
    
    # 1. 加载评测用例
    with open(dataset_path, 'r', encoding='utf-8') as f:
        eval_cases = [EvalCase(**case) for case in json.load(f)]
    
    # 2. 运行评测
    evaluator = EndToEndEvaluator(agent, eval_cases)
    report = await evaluator.run_evaluation()
    
    # 3. 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"eval_reports/eval_{timestamp}.md", 'w', encoding='utf-8') as f:
        f.write(report)
    
    # 4. 检查是否通过基准线
    avg_score = parse_overall_score(report)
    if avg_score < 3.5:  # 基准线
        print(f"⚠️  警告: 综合评分 {avg_score:.2f} 低于基准线 3.5")
    else:
        print(f"✅ 通过: 综合评分 {avg_score:.2f} 达到基准线")
    
    return report
```

## 典型应用场景

### 场景 1: 提示词优化前后的对比评测

```python
# 版本 A: 原始提示词
agent_v1 = ReActAgent(sys_prompt="你是一个助手", ...)

# 版本 B: 优化后的提示词
agent_v2 = ReActAgent(sys_prompt="你是一个专业的课程研究助理...", ...)

# 对比评测
results_v1 = await evaluator_v1.run_evaluation()
results_v2 = await evaluator_v2.run_evaluation()

print(f"V1 综合评分: {results_v1['overall']}")
print(f"V2 综合评分: {results_v2['overall']}")
print(f"改进: {results_v2['overall'] - results_v1['overall']:.2f}")
```

### 场景 2: 回归测试 (防止退化)

```python
# 每次修改Agent后运行回归测试
def regression_test(agent, baseline_scores):
    """回归测试: 确保修改没有导致性能退化"""
    
    evaluator = EndToEndEvaluator(agent, eval_dataset)
    current_report = await evaluator.run_evaluation()
    current_scores = parse_scores(current_report)
    
    for metric, score in current_scores.items():
        baseline = baseline_scores[metric]
        if score < baseline * 0.9:  # 允许10%的波动
            print(f"⚠️  回归: {metric} 从 {baseline:.2f} 降到 {score:.2f}")
            return False
    
    print("✅ 回归测试通过")
    return True
```

### 场景 3: 持续改进循环

```python
async def continuous_improvement_loop(agent, eval_dataset):
    """持续改进循环: 评测 → 分析 → 优化 → 再评测"""
    
    for iteration in range(10):
        print(f"\n=== 迭代 {iteration + 1} ===")
        
        # 1. 评测
        report = await run_evaluation(agent, eval_dataset)
        scores = parse_scores(report)
        
        # 2. 分析短板
        weakest_metric = min(scores, key=scores.get)
        print(f"最弱指标: {weakest_metric} ({scores[weakest_metric]:.2f})")
        
        # 3. 针对性优化
        optimization = generate_optimization(weakest_metric)
        agent = apply_optimization(agent, optimization)
        
        # 4. 检查是否达标
        if all(score >= 4.0 for score in scores.values()):
            print("✅ 所有指标达标,停止优化")
            break
```

## 评测指标体系

### 端到端指标

| 指标 | 说明 | 目标值 |
|------|------|--------|
| 输出质量 | 最终回复是否满足用户需求 | ≥4.0/5.0 |
| 工具调用准确率 | 是否调用了合适的工具 | ≥4.0/5.0 |
| 执行效率 | 是否避免了不必要的调用 | ≥3.5/5.0 |
| 综合评分 | 以上三项的平均值 | ≥3.8/5.0 |

### 白盒化指标

| 指标 | 说明 | 目标值 |
|------|------|--------|
| ReAct循环次数 | 完成任务所需的循环数 | 3-8次 |
| 工具调用路径 | 工具调用序列是否合理 | 与专家路径匹配≥80% |
| 决策质量 | 每次工具调用的合理性 | ≥85% |
| 错误率 | 工具调用失败的比例 | ≤5% |

## 最佳实践

### 1. 构建有代表性的评测集

- **覆盖各类场景**: 简单查询、复杂任务、边界情况
- **包含困难梯度**: easy, medium, hard
- **定期更新**: 加入新出现的用例

### 2. 自动化评测流程

- **CI/CD 集成**: 每次代码提交后自动运行评测
- **基准线管理**: 设定最低标准,防止退化
- **报告生成**: 自动生成可读的评测报告

### 3. 人机结合

- **自动评分**: 使用规则或评判模型自动评分
- **人工复核**: 定期对自动评分结果进行人工校验
- **持续校准**: 根据人工反馈校准自动评分系统

## 相关资源

- [LLM 评测框架综述](https://arxiv.org/abs/2307.03381)
- [AgentScope 评测文档](https://github.com/agentscope-ai/agentscope)
