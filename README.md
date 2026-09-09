# Agent 智能体系统

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 📖 项目简介

基于 AgentScope 的生产级 Agent 系统。用户自由选择工作流，所有工作流共享同一套工具、记忆和评测基础设施。

**核心理念**: 不是让 Agent 知道更多事实（那是 RAG 的事），而是让 Agent 知道**该怎么做**。

## 🏗️ 架构

```
用户 (Web UI / CLI)
    │
    ▼ 自由选择
┌────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐
│ ReAct  │ │Planning  │ │Parallel │ │Hierarch- │ │CoCreate  │ │External       │
│ Agent  │ │Notebook  │ │Review   │ │  ical    │ │  ion     │ │Feedback       │
└────────┘ └──────────┘ └─────────┘ └──────────┘ └──────────┘ └───────────────┘
    │          │           │           │            │             │
    └──────────┴───────────┴─────┬─────┴────────────┴─────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │     共享基础设施         │
                    │  工具: MCP/Skill/动态    │
                    │  记忆: 短期 + 长期       │
                    │  评测: 端到端 + 白盒化   │
                    └─────────────────────────┘
```

| 工作流 | 适用场景 |
|--------|---------|
| **ReAct Agent** | 简单问答，直接回答或搜索 |
| **Planning Notebook** | 复杂多步任务，Agent 自主拆解和执行 |
| **Parallel Review** | 4 个专家并行评估 (代码/事实/风格/教学法) |
| **Hierarchical** | Leader-Worker 层级分工 |
| **Co-creation** | MsgHub 圆桌共创，多轮迭代 |
| **MoA** | 3 模型并行 + 聚合器，追求极致质量 |
| **External Feedback** | 润色含代码文档，自动验证代码正确性 |

## 🚀 快速开始

```bash
conda create -n agent_learn python=3.10 && conda activate agent_learn
pip install -r requirements.txt
cp .env.example .env  # 填入 DASHSCOPE_API_KEY
```

### Web UI (推荐)

```bash
pip install gradio
python scripts/run_web.py
# 打开 http://127.0.0.1:7860
```

### CLI

```bash
python scripts/run_agent.py -i -m react         # ReAct
python scripts/run_agent.py -i -m hierarchical  # 层级协作
python scripts/run_agent.py -i -m cocreation    # 圆桌共创
```

### 评测

```bash
python scripts/run_eval.py
```

## 📁 项目结构

```
Agent/
├── src/
│   ├── config.py                # 配置管理
│   ├── agent_engine/
│   │   ├── react_agent.py       # ReAct Agent
│   │   ├── agent_system.py      # 统一智能体
│   │   └── agent_factory.py     # Research/Review/Planning Agent
│   ├── tools/
│   │   ├── tool_manager.py      # MCP + Skill 注册
│   │   └── mcp_client.py        # MCP 客户端
│   ├── planning/
│   │   ├── reflection.py        # Self-Review + External Feedback
│   │   ├── workflow.py          # Pipeline/Branch/Parallel/MoA/HITL
│   │   ├── plan_notebook.py     # 自主规划
│   │   └── dynamic_tools.py     # 动态工具创建
│   ├── orchestration/
│   │   ├── hierarchical.py      # HierarchicalTeam
│   │   └── cocreation.py        # CoCreationTeam
│   ├── memory/
│   │   ├── short_term.py        # 截断/摘要
│   │   └── long_term.py         # Mem0 + Qdrant
│   ├── skills/
│   │   └── skill_loader.py      # 本地加载 + 社区搜索/安装
│   ├── evaluation/
│   │   └── evaluator.py         # 端到端 + 白盒化
│   └── api/
│       ├── app.py               # FastAPI
│       └── schemas.py
├── scripts/
│   ├── run_agent.py             # CLI
│   ├── run_web.py               # Gradio Web UI
│   ├── run_planning.py          # 规划演示
│   ├── run_eval.py              # 评测
│   └── run_mcp_server.py        # MCP Server
├── skills/course-review/SKILL.md
├── mcp_servers/web_search_server.py
└── data/eval_cases.json
```

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| Agent 框架 | AgentScope (ReActAgent, Toolkit, MsgHub, PlanNotebook) |
| 大模型 | 阿里云 DashScope (qwen-plus) |
| 工具协议 | MCP (StdIOStatefulClient, HttpStatelessClient) |
| 向量存储 | Qdrant |
| 嵌入模型 | DashScope text-embedding-v4 (2048 维) |
| 记忆管理 | Mem0 |
| Web UI | Gradio |
| Web API | FastAPI + Uvicorn |

## 📚 学习资源

基于 [阿里云大模型 ACP 认证课程](https://edu.aliyun.com/course/3130200):
- C2: RAG 原理与实践
- C3: Agent 设计与开发
- C4: 模型优化与上线

## 📄 许可证

MIT License
