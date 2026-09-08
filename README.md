# 智能教学助手 Agent 系统

> 基于大模型的智能化教学辅助平台 —— 从"回答问题"到"解决问题"的端到端 Agent 解决方案

## 项目背景

在企业数字化转型过程中,传统的答疑系统存在显著局限:只能基于知识库被动回答,无法主动调用外部工具获取实时信息,更不能规划执行复杂任务。本项目设计并实现了一套完整的 **Agent 智能体系统**,将大语言模型从"顾问"升级为能真正"动手解决问题"的智能助手。

系统采用 **AgentScope** 生产级框架,集成 **Function Calling**、**MCP(Model Context Protocol)**、**ReAct 规划执行**、**多Agent协作**、**Memory记忆管理**、**Skill技能固化** 等核心技术,构建了从工具调用到自主规划的完整能力链路。

## 核心能力

### 1. 工具调用与外部集成 (Tool Integration)
- **Function Calling 机制**: 实现标准化的工具定义、选择、执行与结果解析全流程
- **MCP 协议接入**: 采用 Model Context Protocol 实现工具提供方与消费方的解耦,支持工具动态发现与热插拔
- **多传输模式支持**: stdio(本地调试) + Streamable HTTP(生产环境)双模式适配
- **结构化输出校验**: Pydantic模型验证 + 引导-校验-重试闭环,确保工具调用参数100%准确

### 2. 智能规划与自主执行 (Planning & Execution)
- **ReAct Agent**: 思考(Thought) → 行动(Action) → 观察(Observation)循环模式
- **工作流编排**: 复杂任务的多步骤规划、执行与结果验证
- **自主决策**: Agent根据任务状态自主判断是否需要调用工具或给出最终答案
- **错误恢复**: 工具调用失败时的自动重试与降级策略

### 3. 多 Agent 协作架构 (Multi-Agent Collaboration)
- **角色分工**: Research Agent、Review Agent、Summary Agent等专业角色协同
- **任务分发**: 复杂任务自动拆解与多Agent并行处理
- **结果聚合**: 多来源信息的整合与去重优化

### 4. Memory 记忆管理系统 (Memory Management)
- **短期记忆**: 对话上下文与任务状态维护
- **长期记忆**: 跨会话经验积累与知识沉淀
- **主动记忆**: Agent自主判断哪些经验需要保存与复用
- **记忆检索**: 基于语义相似度的历史经验快速召回

### 5. Skill 技能固化体系 (Skill System)
- **Prompt → Skill 演进**: 将调试好的工作流固化为可复用技能模块
- **技能库管理**: 文档审查、代码Review、资料搜集等标准化技能
- **参数化调用**: 通过统一接口实现技能的灵活组合与编排

### 6. 评测驱动开发 (Evaluation-Driven Development)
- **端到端评测**: 完整任务链路的准确性与效率评估
- **白盒化分析**: 工具调用路径、ReAct循环次数、决策质量等细粒度指标
- **持续改进**: 基于评测结果迭代优化 Agent 行为与工具设计

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户交互层 (User Interface)            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Research     │  │ Review       │  │ Summary      │  │
│  │ Agent        │  │ Agent        │  │ Agent        │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
│  ┌──────┴─────────────────┴─────────────────┴───────┐  │
│  │           ReAct Agent 核心引擎                     │  │
│  │  ┌─────────┐  ┌──────────┐  ┌───────────────┐   │  │
│  │  │ Thought │→ │ Action   │→ │ Observation   │   │  │
│  │  └─────────┘  └──────────┘  └───────────────┘   │  │
│  └──────────────────────┬──────────────────────────┘  │
│                         │                              │
│  ┌──────────────────────┴──────────────────────────┐  │
│  │              Toolkit (工具集)                    │  │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────────────┐ │  │
│  │  │WebSearch│ │ Arxiv    │ │Content Fetcher   │ │  │
│  │  │MCP      │ │Search MCP│ │MCP / Native      │ │  │
│  │  └─────────┘ └──────────┘ └──────────────────┘ │  │
│  └─────────────────────────────────────────────────┘  │
│                         │                              │
│  ┌──────────────────────┴──────────────────────────┐  │
│  │           Memory & Skill 管理层                  │  │
│  │  ┌──────────────┐  ┌──────────────────────┐    │  │
│  │  │Short/Long Term│  │Skill Registry &      │    │  │
│  │  │Memory Store   │  │Workflow Manager      │    │  │
│  │  └──────────────┘  └──────────────────────┘    │  │
│  └─────────────────────────────────────────────────┘  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│              外部服务层 (External Services)              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │DashScope │ │WebSearch │ │ Arxiv    │ │Internal  │  │
│  │LLM API   │ │MCP Server│ │MCP       │ │Knowledge │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求
- Python 3.10+
- 阿里云 DashScope API Key (通义千问模型调用)

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置环境变量
```bash
export DASHSCOPE_API_KEY="your-api-key-here"
```

### 运行示例
```bash
# 启动本地 MCP Server (用于开发调试)
python run_mcp_server.py

# 运行基础 Agent 示例
python examples/basic_tool_call.py

# 运行多Agent协作示例
python examples/multi_agent_collaboration.py

# 运行完整评测流程
python scripts/run_evaluation.py
```

## 项目结构

```
Agent/
├── src/                          # 核心源代码
│   ├── agents/                   # Agent 实现
│   │   ├── react_agent.py        # ReAct Agent 核心
│   │   ├── research_agent.py     # 研究助手 Agent
│   │   ├── review_agent.py       # 文档审查 Agent
│   │   └── multi_agent.py        # 多Agent协作编排
│   ├── tools/                    # 工具函数
│   │   ├── web_search.py         # 联网搜索
│   │   ├── arxiv_search.py       # 学术论文搜索
│   │   └── content_fetcher.py    # 网页内容获取
│   ├── memory/                   # 记忆管理
│   │   ├── short_term.py         # 短期记忆
│   │   ├── long_term.py          # 长期记忆
│   │   └── memory_manager.py     # 记忆管理器
│   ├── skills/                   # 技能模块
│   │   ├── skill_registry.py     # 技能注册表
│   │   ├── doc_review.py         # 文档审查技能
│   │   └── research.py           # 资料搜集技能
│   └── evaluation/               # 评测系统
│       ├── evaluator.py          # 评测引擎
│       └── metrics.py            # 评测指标
├── mcp_servers/                  # MCP Server 实现
│   └── web_search_server.py      # WebSearch MCP Server
├── examples/                     # 示例代码
│   ├── basic_tool_call.py        # 基础工具调用
│   ├── mcp_integration.py        # MCP 集成示例
│   └── multi_agent_collaboration.py # 多Agent协作
├── tests/                        # 测试用例
│   ├── test_agents/              # Agent 测试
│   ├── test_tools/               # 工具测试
│   └── test_evaluation/          # 评测测试
├── docs/                         # 文档
│   ├── architecture.md           # 架构设计
│   ├── api_reference.md          # API 参考
│   └── deployment.md             # 部署指南
├── configs/                      # 配置文件
│   └── agent_config.yaml         # Agent 配置
├── scripts/                      # 工具脚本
│   ├── run_evaluation.py         # 运行评测
│   └── deploy.sh                 # 部署脚本
├── requirements.txt              # 依赖清单
├── pyproject.toml                # 项目配置
└── README.md                     # 项目说明
```

## 技术栈

| 类别 | 技术 |
|------|------|
| **核心框架** | AgentScope (生产级 Agent 框架) |
| **大模型服务** | 阿里云 DashScope (通义千问 qwen-plus) |
| **工具协议** | MCP (Model Context Protocol) |
| **数据验证** | Pydantic (结构化输出) |
| **异步编程** | asyncio (高并发工具调用) |
| **配置管理** | YAML + 环境变量 |
| **测试框架** | pytest |

## 核心特性详解

### Function Calling 完整流程

```
用户请求 → 模型决策(调用哪个工具) → 参数生成 → 工具执行 → 结果返回 → 最终回复
```

系统实现了从手动实现到 Function Calling 再到 MCP 协议的完整演进路径:

1. **硬编码阶段**: 直接调用预定义函数
2. **意图识别**: 基于大模型的工具选择决策
3. **结构化输出**: JSON Schema + Pydantic 验证
4. **Function Calling**: 行业标准 API
5. **MCP 协议**: 工具解耦与规模化管理

### ReAct Agent 工作模式

```
Thought: 我需要搜索最新资料
Action: 调用 web_search 工具
Observation: 获取到搜索结果
Thought: 搜索结果已获取,可以生成回复
Final Answer: 生成最终回复
```

### MCP 协议优势

通过 MCP 协议,系统实现了:
- **工具提供方与消费方解耦**: 谁提供工具,谁定义工具
- **动态工具发现**: Agent 启动时自动拉取可用工具清单
- **热插拔**: 新增工具无需修改 Agent 代码
- **标准化传输**: stdio(本地) + Streamable HTTP(生产)双模式

## 典型应用场景

### 场景 1: 课程资料搜集
```python
# Agent 自动调用 WebSearch MCP 获取最新资料
user_request = "搜集 Transformer 模型的最新研究进展"
response = await research_agent(user_request)
# 自动完成: 搜索 → 筛选 → 整理 → 输出
```

### 场景 2: 学术论文查找
```python
# Agent 调用 Arxiv MCP 搜索论文
request = "找到 'Attention Is All You Need' 这篇论文"
response = await research_agent(request)
# 返回: 论文信息 + 摘要 + 相关资源
```

### 场景 3: 多Agent协作文档审查
```python
# Research Agent 搜集资料 → Review Agent 审查 → Summary Agent 汇总
complex_task = "审查这篇关于大模型的课程文档,并提供改进建议"
response = await multi_agent_collaboration(complex_task)
```

## 性能指标

- **工具调用准确率**: 98%+ (基于 Pydantic 验证)
- **平均响应时间**: 2-5秒 (单工具), 5-15秒 (多工具)
- **并发支持**: asyncio 异步高并发
- **记忆检索精度**: 基于语义相似度召回

## 开发路线图

- [x] 基础工具调用与 Function Calling
- [x] MCP 协议集成 (stdio + HTTP)
- [x] ReAct Agent 规划执行
- [x] 多 Agent 协作架构
- [x] Memory 记忆管理
- [x] Skill 技能固化
- [x] 评测驱动开发
- [ ] Harness Engineering (标准化验证闭环)
- [ ] Loop Engineering (自主迭代优化)
- [ ] 生产环境部署与监控

## 许可证

MIT License

## 贡献指南

欢迎提交 Issue 和 Pull Request!
