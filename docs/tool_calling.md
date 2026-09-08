# 工具调用模块文档

## 概述

工具调用模块是 Agent 系统的核心基础,它使大语言模型能够突破纯文本对话的限制,主动与外部环境交互,实现真正的"动手解决问题"能力。

## 架构设计

### 1. 工具调用演进路径

本项目实现了从简单到复杂的完整工具调用机制:

```
硬编码调用 → 意图识别 → 结构化输出 → Function Calling → MCP协议
```

#### 阶段 1: 硬编码调用 (Hardcoded Invocation)
- **适用场景**: 单一工具、固定流程
- **实现方式**: 直接在业务代码中调用工具函数
- **局限性**: 无法动态选择工具,扩展性差

```python
# 硬编码示例
user_request = "搜集 Transformer 模型资料"
tool_result = web_search(query=user_request)
response = llm.generate(prompt=f"请求: {user_request}\n结果: {tool_result}")
```

#### 阶段 2: 意图识别 (Intent Recognition)
- **核心思想**: 让大模型决定使用哪个工具
- **实现方式**: 在 Prompt 中列出工具,让模型决策
- **优势**: 支持多工具动态选择

```python
def get_tool_decision(user_request):
    prompt = f"""
    从以下工具中选择最合适的:
    1. web_search: 通用信息搜索
    2. search_arxiv_paper: 学术论文搜索
    3. fetch_webpage_content: 网页内容获取
    
    用户请求: "{user_request}"
    请告诉我要使用哪个工具及参数。
    """
    return llm.generate(prompt)
```

#### 阶段 3: 结构化输出 (Structured Output)
- **问题**: 模型输出格式不固定,难以解析
- **解决方案**: JSON Schema + Pydantic 验证 + 引导-校验-重试闭环
- **关键组件**:
  - Pydantic 模型定义工具参数结构
  - JSON 格式强制约束
  - 验证失败时自动重试

```python
from pydantic import BaseModel, Field
from typing import Union, Literal

class WebSearchParams(BaseModel):
    query: str = Field(description="搜索关键词")

class WebSearchCall(BaseModel):
    tool_name: Literal["web_search"]
    parameters: WebSearchParams

# 引导-校验-重试闭环
def get_structured_output(user_request, max_retries=2):
    for attempt in range(max_retries):
        response = llm.generate(build_prompt(user_request))
        try:
            data = json.loads(response)
            validated = WebSearchCall.model_validate(data)
            return validated.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            # 将错误信息反馈给模型,要求重新生成
            messages.extend([
                {'role': 'assistant', 'content': response},
                {'role': 'user', 'content': f"格式错误: {e}"}
            ])
```

#### 阶段 4: Function Calling (行业标准)
- **标准**: OpenAI/阿里云等厂商内置 API
- **工作流程**:
  1. 在 `tools` 参数中定义工具 (JSON Schema)
  2. 模型自动决策是否调用工具
  3. 解析 `tool_calls` 字段获取工具名和参数
  4. 执行工具,将结果以 `role: "tool"` 传回
  5. 模型基于工具结果生成最终回复

```python
tools = [{
    "type": "function",
    "function": {
        "name": "search_arxiv_paper",
        "description": "在 Arxiv.org 搜索学术论文",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "论文标题或关键词"}
            },
            "required": ["query"]
        }
    }
}]

# 第一次调用: 让模型决策
response = client.chat.completions.create(
    model="qwen-plus", 
    messages=messages, 
    tools=tools, 
    tool_choice="auto"
)

# 检查是否调用工具
if response.choices[0].message.tool_calls:
    tool_call = response.choices[0].message.tool_calls[0]
    function_args = json.loads(tool_call.function.arguments)
    tool_result = execute_tool(tool_call.function.name, function_args)
    
    # 第二次调用: 将工具结果传回
    messages.append(response.choices[0].message)
    messages.append({
        "tool_call_id": tool_call.id,
        "role": "tool",
        "name": tool_call.function.name,
        "content": tool_result
    })
    final_response = client.chat.completions.create(
        model="qwen-plus", 
        messages=messages
    )
```

#### 阶段 5: MCP 协议 (规模化管理)
- **问题**: Function Calling 需要在 Agent 侧硬编码工具 Schema,维护成本高
- **解决方案**: Model Context Protocol (模型上下文协议)
- **核心思想**: 谁提供工具,谁定义工具 (职责分离)
- **架构角色**:
  - **MCP Server**: 工具提供方,声明工具名称、描述、参数
  - **MCP Client**: 工具消费方,连接 Server 拉取工具定义
  - **Agent**: 通过 Client 动态发现工具,无需硬编码

```python
# MCP Server (工具提供方)
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("WebSearch")

@mcp.tool()
def web_search(query: str, max_results: int = 3) -> str:
    """模拟联网搜索"""
    # 实现搜索逻辑
    return search_results

# MCP Client (工具消费方)
from agentscope.mcp import StdIOStatefulClient

web_search_client = StdIOStatefulClient(
    name="web_search_service",
    command=sys.executable,
    args=["mcp_server.py"]
)
await web_search_client.connect()

# Agent 启动时自动发现工具
toolkit = Toolkit()
await toolkit.register_mcp_client(web_search_client)

agent = ReActAgent(toolkit=toolkit, ...)
```

### 2. ReAct 模式 (思考-行动-观察)

Function Calling 的本质是实现 **ReAct 循环**:

```
Thought (思考): 任务是否完成? 是否需要调用工具?
    ↓
Action (行动): 调用工具,生成中间结果
    ↓
Observation (观察): 工具返回结果
    ↓
Thought (思考): 基于观察结果,下一步做什么?
```

**手动实现 vs 框架封装**:

| 维度 | 手动实现 | AgentScope 框架 |
|------|---------|----------------|
| 代码复杂度 | 高 (状态管理、多轮调用、错误重试) | 低 (框架自动处理) |
| 工具定义 | 手动编写 JSON Schema | 自动从 Python 函数文档字符串解析 |
| 对话历史 | 手动维护 | 自动记录 |
| 多轮工具调用 | 需自行实现循环 | 内置支持 |
| 调试难度 | 高 | 低 (有日志和可视化) |

**推荐使用 AgentScope 框架**:

```python
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import DashScopeChatModel

# 定义工具 (普通 Python 函数)
def search_arxiv_paper(query: str):
    """在 Arxiv.org 搜索学术论文。
    
    Args:
        query (str): 搜索关键词
    """
    # 实现搜索逻辑
    return ToolResponse(content=[...])

# 注册工具并创建 Agent
toolkit = Toolkit()
toolkit.register_tool_function(search_arxiv_paper)

agent = ReActAgent(
    name="Research Agent",
    sys_prompt="你是一个课程研究助理",
    model=DashScopeChatModel(model_name="qwen-plus"),
    toolkit=toolkit
)

# 发送消息,Agent 自动完成所有步骤
response = await agent(Msg(name="user", content="搜索 Transformer 论文", role="user"))
```

### 3. MCP 传输模式

#### stdio 模式 (本地调试)
- **适用场景**: 本地开发调试、IDE 集成 (如 Cursor、Claude Desktop)
- **通信方式**: 标准输入/输出 (stdin/stdout)
- **特点**: Server 和 Client 在同一进程树

```python
client = StdIOStatefulClient(
    name="web_search_service",
    command=sys.executable,
    args=["mcp_server.py"]
)
await client.connect()
```

#### Streamable HTTP 模式 (生产环境)
- **适用场景**: 远程服务、多用户共享、生产部署
- **通信方式**: HTTP 流式传输
- **特点**: Server 部署在远端,支持认证和鉴权

```python
client = HttpStatelessClient(
    name="web_search_service",
    transport="streamable_http",
    url="https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp",
    headers={"Authorization": "Bearer " + os.environ["DASHSCOPE_API_KEY"]}
)
```

## API 参考

### 工具函数定义

```python
def tool_name(param1: type, param2: type = default) -> ToolResponse:
    """工具描述。
    
    Args:
        param1: 参数1描述
        param2: 参数2描述
    
    Returns:
        ToolResponse: 工具执行结果
    """
    return ToolResponse(content=[TextBlock(type="text", text="结果")])
```

### Function Calling 调用流程

```python
# 1. 定义工具
tools = [{
    "type": "function",
    "function": {
        "name": "tool_name",
        "description": "工具描述",
        "parameters": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }
}]

# 2. 第一次调用 (决策)
response = client.chat.completions.create(
    model="qwen-plus",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)

# 3. 执行工具
if response.choices[0].message.tool_calls:
    tool_result = execute_tool(...)
    
    # 4. 第二次调用 (生成回复)
    messages.append(response.choices[0].message)
    messages.append({"role": "tool", "content": tool_result})
    final_response = client.chat.completions.create(messages=messages)
```

## 最佳实践

### 1. JSON Schema 设计原则

- **清晰的描述**: `description` 字段要让模型理解工具用途
- **必填参数**: `required` 数组明确哪些参数必须有
- **类型约束**: 使用 `type`, `enum`, `minimum`, `maximum` 等约束
- **示例值**: 在 `description` 中提供示例值帮助模型理解

```python
"parameters": {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词,例如 'Transformer model latest research'"
        },
        "max_results": {
            "type": "integer",
            "description": "最大返回结果数量",
            "minimum": 1,
            "maximum": 10,
            "default": 5
        }
    },
    "required": ["query"]
}
```

### 2. 错误处理策略

- **验证失败**: 将错误信息反馈给模型,要求重新生成
- **工具执行失败**: 记录错误日志,返回友好错误信息
- **超时处理**: 设置合理的超时时间,避免无限等待

```python
try:
    result = execute_tool(tool_name, params)
except ToolExecutionError as e:
    return ToolResponse(
        content=[TextBlock(type="text", text=f"工具执行失败: {str(e)}")]
    )
```

### 3. 工具组合策略

- **单一职责**: 每个工具只做一件事
- **可组合**: 工具之间可以互相调用
- **降级方案**: 当某个工具不可用时的备选策略

## 故障排查

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 模型不调用工具 | 工具描述不清晰 | 优化 `description` 字段 |
| 参数生成错误 | Schema 约束不够 | 添加 `type`, `required`, `enum` 等约束 |
| 工具执行失败 | 参数格式不对 | 使用 Pydantic 验证参数 |
| MCP 连接失败 | Server 未启动 | 检查 Server 进程和传输模式 |

## 相关资源

- [AgentScope 官方文档](https://github.com/agentscope-ai/agentscope)
- [MCP 协议规范](https://modelcontextprotocol.io/specification)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
