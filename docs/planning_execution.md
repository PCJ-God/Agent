# 规划与执行模块文档

## 概述

规划与执行模块赋予 Agent **自主决策和分步执行复杂任务**的能力。通过 ReAct (Reasoning + Acting) 循环,Agent 能够像人类一样"先思考、再行动、根据结果调整策略",而非简单的一问一答。

## 核心概念

### 为什么需要规划能力?

基础的 Function Calling 只能完成**单步或少量工具调用**的简单任务。面对复杂需求时:

```
用户请求: "帮我搜集 Transformer 模型的最新研究进展,整理成课程大纲,
         并审查内容是否覆盖了核心知识点,最后生成教学建议。"
```

这个请求需要:
1. 搜索资料 (多次工具调用)
2. 整理信息 (结构化处理)
3. 生成大纲 (创作任务)
4. 审查内容 (质量检查)
5. 生成建议 (分析任务)

没有规划能力的 Agent 会"一口气做完就结束",而具备规划能力的 Agent 会:
- **分解任务**: 将大任务拆分为多个子任务
- **有序执行**: 按依赖关系依次执行
- **质量检查**: 每步验证结果是否达标
- **迭代优化**: 发现问题时主动修正

## ReAct 循环详解

### 工作模式

```
┌─────────────────────────────────────────────────────┐
│                  ReAct 循环                          │
│                                                      │
│  ┌──────────┐                                        │
│  │ Thought  │ ← 我现在要做什么? 是否需要调用工具?    │
│  └────┬─────┘                                        │
│       ↓                                              │
│  ┌──────────┐                                        │
│  │ Action   │ ← 调用工具 / 生成中间结果              │
│  └────┬─────┘                                        │
│       ↓                                              │
│  ┌──────────┐                                        │
│  │Observation│ ← 工具返回了什么? 任务完成了吗?       │
│  └────┬─────┘                                        │
│       ↓                                              │
│  ┌──────────┐                                        │
│  │ Thought  │ ← 基于观察,下一步做什么?              │
│  └──────────┘                                        │
│                                                      │
│  循环直到 → Final Answer (最终回复)                   │
└─────────────────────────────────────────────────────┘
```

### 完整执行示例

**用户请求**: "搜集关于 Transformer 模型的教学资料"

```
[Thought 1] 用户需要搜集 Transformer 模型的教学资料。
           我需要先搜索最新的研究进展和教学资源。
           我应该使用 web_search 工具搜索通用资料,
           使用 search_arxiv_paper 搜索学术论文。

[Action 1] 调用 web_search(query="Transformer model teaching materials latest research")

[Observation 1] 搜索到 5 条相关资料,包括课程大纲、教程链接等。

[Thought 2] 已获取通用资料,接下来需要搜索学术论文。
           我应该搜索经典的 Transformer 论文和最新综述。

[Action 2] 调用 search_arxiv_paper(query="Transformer model survey tutorial")

[Observation 2] 搜索到 3 篇相关论文,包括 "Attention Is All You Need" 等。

[Thought 3] 已搜集到足够的资料,现在需要整理并生成教学大纲。
           我可以基于搜索结果生成结构化的教学建议。

[Final Answer] 为您整理了 Transformer 模型教学资料:
              1. 核心论文: ...
              2. 教学资源: ...
              3. 建议学习路径: ...
```

## 实现方案

### 方案 1: 手动实现 ReAct Agent

手动实现需要管理状态、多轮调用和循环逻辑:

```python
def react_agent(user_request):
    messages = [{"role": "user", "content": user_request}]
    
    max_turns = 10
    for turn in range(max_turns):
        # 1. 让模型决策
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=messages,
            tools=tools
        )
        
        message = response.choices[0].message
        
        # 2. 检查是否有工具调用
        if not message.tool_calls:
            # 没有工具调用,说明已生成最终答案
            return message.content
        
        # 3. 执行工具
        tool_call = message.tool_calls[0]
        tool_result = execute_tool(tool_call.function.name, 
                                   json.loads(tool_call.function.arguments))
        
        # 4. 将结果加入对话历史
        messages.append(message)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": tool_result
        })
    
    return "达到最大循环次数,任务未完成"
```

**手动实现的挑战**:
- 状态管理复杂 (需要记录每轮对话和工具调用)
- 错误处理繁琐 (重试、降级、超时)
- 循环终止条件难以判断
- 难以调试 (不知道 Agent 为什么做某个决策)

### 方案 2: 使用 AgentScope 框架 (推荐)

AgentScope 内置完整的 ReAct Agent,自动处理所有复杂逻辑:

```python
import asyncio
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import DashScopeChatModel
from agentscope.message import Msg

async def run_react_agent():
    # 1. 定义工具
    def web_search(query: str) -> ToolResponse:
        """联网搜索最新资料。
        
        Args:
            query (str): 搜索关键词
        """
        print(f"--- 正在搜索: {query} ---")
        # 实现搜索逻辑
        return ToolResponse(content=[TextBlock(type="text", text="搜索结果")])
    
    # 2. 注册工具
    toolkit = Toolkit()
    toolkit.register_tool_function(web_search)
    
    # 3. 创建 ReActAgent
    agent = ReActAgent(
        name="Research Agent",
        sys_prompt="""你是一个课程研究助理,擅长搜集和整理教学资料。
你的工作流程:
1. 理解用户需求
2. 使用工具搜集相关资料
3. 整理和汇总搜集到的信息
4. 生成结构化的教学建议""",
        model=DashScopeChatModel(
            model_name="qwen-plus",
            api_key=os.environ.get("DASHSCOPE_API_KEY")
        ),
        toolkit=toolkit,
        max_iters=10  # 最大循环次数
    )
    
    # 4. 发送请求,Agent 自动完成所有步骤
    user_request = "搜集 Transformer 模型的最新研究进展和教学资源"
    msg = Msg(name="user", content=user_request, role="user")
    
    print(f"用户请求: {user_request}\n")
    response = await agent(msg)
    
    print(f"\nAgent 回复:\n{response.content}")

asyncio.run(run_react_agent())
```

**框架优势**:
- ✅ 自动管理对话历史和状态
- ✅ 自动解析工具调用和执行结果
- ✅ 自动处理错误重试和超时
- ✅ 支持多轮工具调用 (直到任务完成)
- ✅ 内置日志和调试支持

## 工作流编排

### 反思模式 (Reflection)

反思模式让 Agent 在执行过程中主动检查质量:

```
用户请求 → Agent 执行 → 生成初稿
                            ↓
                    [反思] 质量是否达标?
                     ↙              ↘
                   Yes               No
                    ↓                ↓
              返回结果         修改优化 → 再次反思
```

```python
def reflection_workflow(user_request):
    # 1. Agent 生成初稿
    draft = agent.generate(user_request)
    
    # 2. 反思检查质量
    critique = reflect_agent.generate(
        f"请审查以下内容的质量:\n\n{draft}\n\n"
        "检查项: 1.完整性 2.准确性 3.结构性 4.可读性"
    )
    
    # 3. 根据反馈修改
    if "需要改进" in critique:
        revised = agent.generate(
            f"根据以下反馈修改内容:\n{critique}\n\n原内容:\n{draft}"
        )
        return revised
    
    return draft
```

### 自主规划模式

对于更复杂的任务,Agent 可以自主生成执行计划:

```
用户请求 → Agent 分析需求
                ↓
         生成执行计划 (Plan)
         - Step 1: 搜索资料
         - Step 2: 整理大纲
         - Step 3: 审查内容
         - Step 4: 生成建议
                ↓
         按步骤执行 (Execute)
                ↓
         汇总结果 (Final)
```

```python
# Agent 自主规划的系统提示词
sys_prompt = """你是一个智能研究助理,擅长规划和执行复杂任务。

当收到任务时,请遵循以下步骤:
1. 分析任务,生成详细的执行计划
2. 按计划逐步执行,每步验证结果
3. 所有步骤完成后,汇总生成最终报告

记住:
- 主动使用工具搜集信息
- 每步检查质量是否达标
- 发现问题时主动修正"""
```

## 最佳实践

### 1. 系统提示词设计

好的系统提示词是 ReAct Agent 成功的关键:

```python
# ✅ 好的提示词 (清晰、具体、有指引)
sys_prompt = """你是一个课程研究助理。
你的职责:
1. 使用工具搜集最新的教学资料
2. 整理和汇总信息
3. 生成结构化的教学建议

工作流程:
- 先搜索获取资料
- 再整理关键信息
- 最后生成建议

注意:
- 确保信息来源可靠
- 结果要结构化、易于理解"""

# ❌ 差的提示词 (模糊、无指引)
sys_prompt = "你是一个助手。"
```

### 2. 循环次数控制

```python
agent = ReActAgent(
    max_iters=10,  # 设置合理的最大循环次数
    ...
)
```

- **太小**: 任务可能未完成
- **太大**: 可能陷入无限循环
- **建议值**: 5-15 (根据任务复杂度调整)

### 3. 工具粒度

- **单一职责**: 每个工具只做一件事
- **可组合**: 工具之间可以配合
- **返回结构化数据**: 便于 Agent 理解和决策

```python
# ✅ 好的工具设计
def web_search(query: str, max_results: int = 5) -> str:
    """搜索网络资料。返回结构化的搜索结果。"""
    results = search_engine(query)
    return format_results(results)  # 结构化格式

# ❌ 差的工具设计
def web_search(query: str) -> str:
    """搜索网络资料。返回一堆杂乱的文本。"""
    return raw_html_content  # 非结构化,Agent 难以理解
```

## 故障排查

### Agent 陷入循环

**症状**: Agent 反复调用同一个工具,无法生成最终回复

**原因**:
- 工具返回结果不满足 Agent 期望
- 系统提示词没有明确的完成条件

**解决方案**:
- 优化工具返回格式,确保信息完整
- 在提示词中明确完成条件

### Agent 不调用工具

**症状**: Agent 直接生成回复,没有使用工具搜集信息

**原因**:
- 工具描述不清晰,Agent 不知道何时使用
- 任务看起来简单,Agent 认为不需要工具

**解决方案**:
- 优化 `description` 字段,明确工具适用场景
- 在系统提示词中强调使用工具的重要性

## 相关资源

- [ReAct 论文](https://arxiv.org/abs/2210.03629)
- [AgentScope ReActAgent 文档](https://github.com/agentscope-ai/agentscope)
