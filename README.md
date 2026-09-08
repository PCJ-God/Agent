# Agent 智能体系统

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 📖 项目简介

本项目是一个基于 **Agent 架构** 的生产级智能教学助手系统，源自阿里云大模型 ACP 认证课程 C3 的实践与扩展。面向教学辅助场景，帮助教师和学生通过自然语言交互完成资料搜集、文档审查、课程规划等复杂任务。

项目从课程 Notebook 教学代码演进为**生产级 Python 包**，具备模块化架构、工具编排、多 Agent 协作、记忆管理和自动化评测能力。

## ✨ 核心特性

### Agent 引擎
- **ReAct 循环**：思考 → 行动 → 观察，支持最大循环次数和超时控制
- **Function Calling**：工具自动注册（从 docstring 解析 JSON Schema），引导-校验-重试闭环
- **MCP 协议集成**：支持 stdio（本地开发）和 Streamable HTTP（生产环境）两种传输模式

### 编排与协作
- **规划执行**：PlanNotebook 计划生成与逐步执行，支持动态工具创建
- **多 Agent 协作**：Hierarchical（层级分发）+ Co-creation（MsgHub 圆桌讨论）两种模式
- **反思模式**：Self-Review（单步自查）+ External Feedback（工具验证）

### 记忆与技能
- **记忆管理**：短期记忆（上下文截断/滚动摘要）+ 长期记忆（Mem0 + Qdrant 向量存储）
- **主动记忆**：Agent 自主决定何时保存和召回（agent_control 模式）
- **Skill 系统**：SKILL.md 文件化定义 + 渐进式披露 + Skills-as-Code 工作流

### 工程化
- **自动化评测**：端到端 + 白盒化，支持 Task + MetricBase + LLMEvalMetric
- **CLI 交互界面**：支持多种 Agent 模式和策略开关
- **Web API 服务**：FastAPI + REST 端点 + SSE 流式输出
- **配置管理**：YAML + 环境变量，集中管理所有参数

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户交互层                                │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │  CLI 交互界面 │  │  Web API 服务 │                             │
│  │ (run_agent.py)│  │ (FastAPI)    │                             │
│  └──────┬───────┘  └──────┬───────┘                             │
└─────────┼────────────────┼──────────────────────────────────────┘
          │                │
┌─────────┼────────────────┼──────────────────────────────────────┐
│         ▼       应用逻辑层        ▼                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Agent 引擎   │  │  编排与协作   │  │  记忆管理     │           │
│  │ (ReActAgent) │  │ (PlanNotebook │  │ (Mem0+Qdrant) │           │
│  │              │  │  MsgHub)      │  │              │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                 │                    │
│  ┌──────┴─────────────────┴─────────────────┴──────┐            │
│  │              技能与工具层                        │            │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │            │
│  │  │ 工具管理  │  │ Skill 库 │  │ MCP 客户端   │  │            │
│  │  │(自动注册) │  │(渐进披露)│  │(stdio/HTTP)  │  │            │
│  │  └──────────┘  └──────────┘  └──────────────┘  │            │
│  └─────────────────────────────────────────────────┘            │
└─────────┼───────────────────────────────────────────────────────┘
          │
┌─────────┼───────────────────────────────────────────────────────┐
│         ▼       评测与存储层      ▼                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  自动化评测   │  │  向量存储     │  │  技能存储     │           │
│  │ (LLMEval)   │  │ (Qdrant)    │  │ (SKILL.md)   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 1. 环境准备

```bash
git clone <your-repo-url>
cd Agent

conda create -n agent_learn python=3.10
conda activate agent_learn
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 DashScope API Key
```

### 3. 运行 Agent

```bash
# CLI 多轮交互 (默认 react 模式)
python scripts/run_agent.py

# CLI 多轮交互 (指定模式)
python scripts/run_agent.py -i -m react         # ReAct 多轮对话 (保留上下文)
python scripts/run_agent.py -i -m hierarchical  # 层级协作 多轮
python scripts/run_agent.py -i -m cocreation    # 圆桌共创 多轮

# 单次提问 (不进入交互模式)
python scripts/run_agent.py -q "帮我搜集 Transformer 模型的教学资料"
python scripts/run_agent.py -q "帮我搜集..." -m hierarchical
```

### 4. 启动 MCP Server

```bash
# 本地 MCP Server（用于开发调试）
python scripts/run_mcp_server.py
```

### 5. 启动 Web API

```bash
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

### 6. 运行评测

```bash
python scripts/run_eval.py              # 默认策略
python scripts/run_eval.py --all        # 对比多种策略
```

## 📡 API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `GET /health` | GET | 健康检查 |
| `POST /chat` | POST | 单轮问答 |
| `POST /chat/stream` | POST (SSE) | 流式问答 |
| `POST /agent/react` | POST | ReAct Agent |
| `POST /agent/hierarchical` | POST | 层级协作 |
| `POST /agent/cocreation` | POST | 圆桌共创 |

## 📁 项目结构

```
Agent/
├── README.md                    # 项目说明
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
│
├── data/                        # 数据
│   ├── eval_cases.json          # 评测用例
│   └── docs/                    # 测试文档
│
├── src/                         # 核心代码
│   ├── config.py                # 配置管理
│   ├── agent_engine/            # Agent 引擎
│   │   ├── react_agent.py       #   ReAct Agent
│   │   └── agent_factory.py     #   Agent 工厂
│   ├── tools/                   # 工具管理
│   │   ├── tool_manager.py      #   工具注册与调用
│   │   └── mcp_client.py        #   MCP 客户端
│   ├── orchestration/           # 编排与协作
│   │   ├── planner.py           #   PlanNotebook 规划
│   │   ├── hierarchical.py      #   层级协作
│   │   └── cocreation.py        #   圆桌共创
│   ├── memory/                  # 记忆管理
│   │   ├── short_term.py        #   短期记忆
│   │   └── long_term.py         #   长期记忆 (Mem0+Qdrant)
│   ├── skills/                  # 技能管理
│   │   ├── skill_loader.py      #   SKILL.md 加载
│   │   └── skill_registry.py    #   技能注册表
│   ├── evaluation/              # 自动化评测
│   │   └── evaluator.py         #   Task + MetricBase
│   └── api/                     # Web API
│       ├── app.py               #   FastAPI 应用
│       └── schemas.py           #   请求/响应模型
│
├── scripts/                     # 运行脚本
│   ├── run_agent.py             # 命令行 Agent
│   ├── run_mcp_server.py        # MCP Server
│   └── run_eval.py              # 自动化评测
│
├── skills/                      # Skill 定义
│   └── course-review/
│       └── SKILL.md
│
└── mcp_servers/                 # MCP Server
    └── web_search_server.py
```

## 🧪 核心功能演示

### ReAct Agent

```python
from src.agent_engine.react_agent import create_react_agent
from src.tools.tool_manager import register_default_tools

agent = create_react_agent()
register_default_tools(agent.toolkit)

response = agent.run("帮我搜集 Transformer 模型的教学资料")
print(response.content)
```

### 多 Agent 协作

```python
# 单次调用 (向后兼容)
from src.orchestration.hierarchical import run_hierarchical
from src.orchestration.cocreation import run_cocreation

result = run_hierarchical("为'大模型原理'设计教学方案")
result = run_cocreation("讨论 Transformer 课程的最佳设计方案")

# 多轮对话 (保留上下文)
from src.orchestration.hierarchical import HierarchicalTeam
from src.orchestration.cocreation import CoCreationTeam
import asyncio

team = HierarchicalTeam()
r1 = asyncio.run(team.chat("搜集资料"))
r2 = asyncio.run(team.chat("你刚才做了什么？"))  # 能记住上下文

team = CoCreationTeam()
summary = asyncio.run(team.discuss("讨论课程设计方案"))
```

### Skill 使用

```python
from src.skills.skill_loader import SkillLoader
from src.agent_engine.react_agent import create_react_agent

loader = SkillLoader()
agent = create_react_agent()

# 注册 Skill（渐进式披露）
loader.register_skill(agent.toolkit, "skills/course-review")

# Agent 自动匹配并执行 Skill
response = agent.run("请审查这份课程文档的质量")
```

## 📊 评测指标

| 指标 | 说明 |
|------|------|
| **Task Completion** | 任务完成率 |
| **Tool Call Accuracy** | 工具调用准确率 |
| **Response Quality** | 回复质量（LLM-as-a-Judge） |
| **Efficiency** | 执行效率（循环次数、耗时） |

## 🛠️ 技术栈

| 类别 | 技术选型 |
|------|----------|
| **编程语言** | Python 3.10+ |
| **Agent 框架** | AgentScope |
| **大模型** | Qwen-Plus / Qwen3-Max |
| **工具协议** | MCP (Model Context Protocol) |
| **向量存储** | Qdrant |
| **嵌入模型** | DashScope text-embedding-v4 |
| **记忆管理** | Mem0 |
| **Web 框架** | FastAPI + Uvicorn |
| **配置管理** | PyYAML + python-dotenv |

## 📚 学习资源

本项目基于 [阿里云大模型 ACP 认证课程](https://edu.aliyun.com/course/3130200) 开发：

- [C2_构造问答系统](https://edu.aliyun.com/course/3130200/) — RAG 原理与实践
- [C3_构建 Agent 系统](https://edu.aliyun.com/course/3130200/) — Agent 设计与开发
- [C4_交付上线](https://edu.aliyun.com/course/3130200/) — 模型优化与上线

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

## 📄 许可证

MIT 许可证，详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [AgentScope](https://github.com/agentscope-ai/agentscope) — Agent 开发框架
- [MCP](https://modelcontextprotocol.io/) — 模型上下文协议
- [阿里云百炼](https://bailian.console.aliyun.com/) — 大模型服务平台
