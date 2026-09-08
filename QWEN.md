# 智能教学助手 Agent 系统 - 项目记忆

## 项目概述
基于 AgentScope 框架的生产级 Agent 解决方案，覆盖从工具调用到 Harness & Loop Engineering 的完整技术链路。

## 技术栈
- **框架**: AgentScope (ReActAgent, Toolkit, MsgHub, PlanNotebook, Evaluate)
- **大模型**: 阿里云 DashScope (qwen-plus, qwen3-max)
- **工具协议**: MCP (FastMCP, StdIOStatefulClient, HttpStatelessClient)
- **向量存储**: Mem0 + Qdrant
- **嵌入模型**: DashScopeTextEmbedding (text-embedding-v4, 2048维)
- **数据验证**: Pydantic

## 项目结构
```
Agent/
├── examples/     # 8个示例文件 (01-07)
├── docs/         # 9个技术文档 (对应课程3.1-3.8)
├── skills/       # Skill 定义 (SKILL.md)
├── mcp_servers/  # MCP Server
├── eval/         # 评测数据集
├── configs/      # 配置文件
└── src/          # 核心代码
```

## 编码规范
- 使用 AgentScope 官方 API，不使用臆想接口
- 所有工具函数必须包含 docstring (AgentScope 自动解析为 JSON Schema)
- 异步函数使用 asyncio，同步函数使用 ToolResponse 返回
- Skill 使用 SKILL.md 格式 (YAML frontmatter + Markdown)

## 常见陷阱
- LLM 无状态: 每次 API 调用独立，需要 Memory 管理
- Attention Dilution: 长上下文导致性能下降
- Lost in the Middle: 中间位置的信息容易被忽略
- LLM-as-a-Judge 偏见: 风格/长度/好人/位置偏见
- 多Agent消耗 3-5x token，需权衡质量与成本

## API Key 配置
环境变量: `DASHSCOPE_API_KEY`
获取方式: https://bailian.console.aliyun.com/
