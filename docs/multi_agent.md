# 多Agent协作模块文档

## 概述

多Agent协作模块通过**角色分工和任务编排**,将复杂工作流拆解为多个专业Agent的协同工作,实现"团队协作"的效果。就像软件开发中的"产品-设计-开发-测试"分工一样,每个Agent专注于自己最擅长的领域。

## 为什么需要多Agent协作?

### 单一Agent的局限

```
用户请求: "为我准备一份关于大模型原理的课程文档,包括理论基础、
         实践案例和课后练习,并审查文档质量后给出改进建议。"
```

单一Agent需要同时完成:
- 搜索资料 (研究能力)
- 编写文档 (写作能力)
- 审查质量 (评审能力)
- 生成建议 (分析能力)

问题:
1. **能力分散**: 一个Agent很难在所有领域都表现出色
2. **上下文混乱**: 多种角色混杂在同一个对话中,容易遗漏信息
3. **质量难控**: 没有独立的审查环节,质量全靠一个Agent的判断

### 多Agent协作的优势

```
┌──────────────────────────────────────────────────────────┐
│                    用户请求                                │
└────────────────────────┬─────────────────────────────────┘
                         ↓
           ┌─────────────────────────────┐
           │    Coordinator Agent        │  ← 任务分解与编排
           │    (协调者)                  │
           └──────┬──────────┬───────────┘
                  ↓          ↓
      ┌───────────────┐  ┌───────────────┐
      │Research Agent │  │ Review Agent  │  ← 专业角色分工
      │ (研究助手)    │  │ (质量审查)    │
      └───────┬───────┘  └───────┬───────┘
              ↓                  ↓
      ┌───────────────┐  ┌───────────────┐
      │ 搜索资料并整理 │  │ 审查并给建议  │
      └───────┬───────┘  └───────┬───────┘
              ↓                  ↓
           ┌─────────────────────────────┐
           │    Summary Agent            │  ← 结果汇总与优化
           │    (汇总者)                  │
           └──────────────┬──────────────┘
                          ↓
                    ┌──────────┐
                    │ 最终输出  │
                    └──────────┘
```

## 架构设计

### 角色定义

#### 1. Research Agent (研究助手)
**职责**: 搜集、筛选、整理相关资料

```python
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import DashScopeChatModel

def create_research_agent():
    toolkit = Toolkit()
    
    # 注册研究相关工具
    toolkit.register_tool_function(web_search)
    toolkit.register_tool_function(search_arxiv_paper)
    toolkit.register_tool_function(fetch_webpage_content)
    
    agent = ReActAgent(
        name="Research Agent",
        sys_prompt="""你是一个专业的课程研究助理,专注于搜集和整理教学资料。

你的职责:
1. 使用搜索工具搜集相关资料
2. 筛选高质量的教学资源
3. 整理关键信息,形成结构化内容
4. 标注资料来源,确保可追溯

注意:
- 优先选择权威来源
- 结果要结构化、易于理解
- 保留重要信息的原始链接""",
        model=DashScopeChatModel(model_name="qwen-plus"),
        toolkit=toolkit
    )
    
    return agent
```

#### 2. Review Agent (质量审查)
**职责**: 检查内容质量,提供改进建议

```python
def create_review_agent():
    # Review Agent 不需要外部工具,只需要大模型的判断能力
    agent = ReActAgent(
        name="Review Agent",
        sys_prompt="""你是一个严格的质量审查官,负责检查教学内容的质量。

审查维度:
1. **完整性**: 是否覆盖了所有必要的知识点
2. **准确性**: 内容是否准确,有无错误或误导性信息
3. **结构性**: 内容组织是否清晰,逻辑是否合理
4. **可读性**: 语言是否简洁,表达是否清晰
5. **实用性**: 是否有实践案例或练习,能否帮助学生理解

审查流程:
1. 仔细阅读待审查的内容
2. 按上述维度逐一评估
3. 给出每个维度的评分 (1-5分)
4. 列出具体的问题和改进建议

输出格式:
- 总体评价
- 各维度评分及说明
- 具体问题清单
- 改进建议""",
        model=DashScopeChatModel(model_name="qwen-plus"),
        toolkit=Toolkit()  # 空工具箱,不需要工具
    )
    
    return agent
```

#### 3. Summary Agent (汇总者)
**职责**: 整合多方信息,生成最终输出

```python
def create_summary_agent():
    agent = ReActAgent(
        name="Summary Agent",
        sys_prompt="""你是一个内容整合专家,擅长将多方信息整合为统一的输出。

你的职责:
1. 接收来自研究Agent的资料整理
2. 接收来自审查Agent的质量反馈
3. 根据质量反馈优化内容
4. 生成最终的、高质量的文档

工作流程:
1. 阅读研究Agent整理的资料
2. 查看审查Agent的反馈
3. 根据反馈优化内容
4. 生成最终的文档""",
        model=DashScopeChatModel(model_name="qwen-plus"),
        toolkit=Toolkit()
    )
    
    return agent
```

### 协作编排

#### 方案 1: 顺序编排 (Sequential)

最简单的编排方式,按顺序依次执行各个Agent:

```python
async def sequential_collaboration(user_request):
    # 1. 创建Agent实例
    research_agent = create_research_agent()
    review_agent = create_review_agent()
    summary_agent = create_summary_agent()
    
    # 2. Research Agent 搜集资料
    print("=== 研究阶段 ===")
    research_result = await research_agent(
        Msg(name="user", content=f"搜集以下主题的资料: {user_request}", role="user")
    )
    
    # 3. Review Agent 审查质量
    print("\n=== 审查阶段 ===")
    review_result = await review_agent(
        Msg(name="research", content=f"请审查以下内容:\n{research_result.content}", role="user")
    )
    
    # 4. Summary Agent 整合输出
    print("\n=== 汇总阶段 ===")
    summary_result = await summary_agent(
        Msg(name="team", content=f"""
        研究结果:
        {research_result.content}
        
        审查反馈:
        {review_result.content}
        
        请根据以上信息生成最终文档。
        """, role="user")
    )
    
    return summary_result
```

#### 方案 2: 条件分支 (Conditional)

根据中间结果决定后续流程:

```python
async def conditional_collaboration(user_request):
    research_agent = create_research_agent()
    review_agent = create_review_agent()
    
    # 1. 研究
    research_result = await research_agent(
        Msg(name="user", content=user_request, role="user")
    )
    
    # 2. 审查
    review_result = await review_agent(
        Msg(name="research", content=str(research_result.content), role="user")
    )
    
    # 3. 根据审查结果决定下一步
    if "需要补充" in review_result.content:
        # 质量不达标,重新搜集资料
        print("审查未通过,需要重新搜集")
        revised_research = await research_agent(
            Msg(name="review", content=f"""
            审查发现以下问题,请重新搜集资料:
            {review_result.content}
            """, role="user")
        )
        return revised_research
    else:
        # 质量达标,直接输出
        print("审查通过,质量达标")
        return research_result
```

#### 方案 3: 并行执行 (Parallel)

多个Agent独立执行,最后汇总结果:

```python
import asyncio

async def parallel_collaboration(user_request):
    research_agent = create_research_agent()
    review_agent = create_review_agent()
    
    # 并行执行两个Agent
    research_task = asyncio.create_task(
        research_agent(Msg(name="user", content=user_request, role="user"))
    )
    review_task = asyncio.create_task(
        review_agent(Msg(name="user", content=f"审查这个请求的要点: {user_request}", role="user"))
    )
    
    # 等待两个Agent都完成
    research_result, review_result = await asyncio.gather(research_task, review_task)
    
    # 汇总结果
    return f"""
    研究结果:
    {research_result.content}
    
    审查意见:
    {review_result.content}
    """
```

## 典型应用场景

### 场景 1: 课程文档审查流水线

```python
async def doc_review_pipeline(document_content):
    """文档审查流水线: 研究 → 审查 → 建议"""
    
    research_agent = create_research_agent()
    review_agent = create_review_agent()
    summary_agent = create_summary_agent()
    
    # 1. 研究: 搜集相关资料和最佳实践
    research_result = await research_agent(
        Msg(name="user", content=f"""
        我正在审查一份关于'{document_content}'的课程文档。
        请帮我搜集该主题的教学最佳实践和常见问题。
        """, role="user")
    )
    
    # 2. 审查: 检查文档质量
    review_result = await review_agent(
        Msg(name="user", content=f"""
        请审查以下课程文档:
        
        {document_content}
        
        同时参考以下教学最佳实践:
        {research_result.content}
        """, role="user")
    )
    
    # 3. 汇总: 生成改进建议
    summary_result = await summary_agent(
        Msg(name="user", content=f"""
        原文档: {document_content}
        研究资料: {research_result.content}
        审查反馈: {review_result.content}
        
        请生成具体的改进建议。
        """, role="user")
    )
    
    return summary_result
```

### 场景 2: 多主题课程资料搜集

```python
async def multi_topic_research(topics):
    """多主题并行研究"""
    
    research_agent = create_research_agent()
    
    # 为每个主题创建独立的研究任务
    tasks = []
    for topic in topics:
        task = asyncio.create_task(
            research_agent(
                Msg(name="user", content=f"搜集'{topic}'的教学资料", role="user")
            )
        )
        tasks.append(task)
    
    # 并行执行所有研究任务
    results = await asyncio.gather(*tasks)
    
    # 汇总所有结果
    summary = "\n\n".join([
        f"主题 {i+1}: {r.content}" 
        for i, r in enumerate(results)
    ])
    
    return summary
```

## 最佳实践

### 1. Agent角色设计原则

- **单一职责**: 每个Agent只负责一类任务
- **专业提示词**: 系统提示词要明确Agent的职责和边界
- **工具隔离**: 只注册该Agent需要的工具,避免滥用

### 2. 协作模式选择

| 场景 | 推荐模式 | 说明 |
|------|---------|------|
| 简单流水线 | Sequential | 步骤固定,依赖关系清晰 |
| 质量检查 | Conditional | 根据质量决定返工或继续 |
| 独立任务 | Parallel | 多个任务互不依赖 |
| 复杂工作流 | 混合模式 | 结合以上多种模式 |

### 3. 信息传递

- **结构化传递**: 将Agent输出整理为结构化数据再传给下一个Agent
- **保留上下文**: 传递足够的上下文,避免信息丢失
- **避免冗余**: 不要传递无关信息,减少干扰

## 故障排查

### Agent之间信息丢失

**症状**: 后一个Agent没有正确使用前一个Agent的输出

**原因**: 信息传递格式不对,或者提示词没有引导使用全部输入

**解决方案**:
- 确保传递完整的Agent输出
- 在系统提示词中明确说明如何使用输入

### Agent角色混乱

**症状**: Agent做了不属于自己职责的事

**原因**: 系统提示词不够清晰,或者工具注册过多

**解决方案**:
- 优化系统提示词,明确Agent的职责边界
- 只注册必要的工具,避免Agent"越权"

## 相关资源

- [Multi-Agent Systems 综述](https://arxiv.org/abs/2309.02427)
- [AgentScope Multi-Agent 文档](https://github.com/agentscope-ai/agentscope)
