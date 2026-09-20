# 智能教学助手 Agent 系统 — 项目记忆

## 项目概述
基于 AgentScope 框架的层级协作 (Hierarchical) Agent 解决方案，采用四层架构设计。

## 四层架构
- **接入层**: CLI / FastAPI 处理用户输入
- **调度层**: Leader Agent 任务拆解、优先级排序、调度执行
- **执行层**: Researcher + Reviewer + MCP 工具 + Skill
- **存储层**: Mem0/Qdrant 长期记忆

## 技术栈
- **框架**: AgentScope (ReActAgent, Toolkit, PlanNotebook)
- **大模型**: 阿里云 DashScope (默认 qwen-plus)
- **工具协议**: MCP (远程 HttpStatelessClient)
- **向量存储**: Mem0 + Qdrant
- **嵌入模型**: DashScopeTextEmbedding (text-embedding-v4, 2048维)
- **数据验证**: Pydantic
- **Web**: FastAPI + Uvicorn

## 编码规范
- 使用 AgentScope 官方 API
- 所有工具函数必须包含 docstring
- 异步函数使用 asyncio，同步函数使用 ToolResponse 返回
- Skill 使用 SKILL.md 格式 (YAML frontmatter + Markdown)
