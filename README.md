# Agent 智能教学助手

一个基于 AgentScope 和 DashScope 的 Agent 实验项目，面向课程资料搜集、课程内容审查、复杂任务规划和多 Agent 协作。项目同时提供 CLI、Gradio 界面和 FastAPI + 原生前端三种使用方式。

项目的重点不是单独封装一个聊天机器人，而是把模型、工具、Skill、记忆、规划、协作和评测组织成可切换的工作流。

## 功能概览

| 能力 | 当前实现 | 入口 |
| --- | --- | --- |
| ReAct 对话 | 思考-行动-观察循环，可注册 MCP 和 Skill 工具 | CLI、Gradio、FastAPI |
| 自主规划 | 使用 `PlanNotebook` 创建计划、执行子任务并记录计划变化 | Gradio、FastAPI、规划演示 |
| 流水线与分支 | 顺序处理或根据请求路由到代码检查、润色、完整审查 | 规划演示 |
| 并行审查 | 代码、事实、教学法、风格四类专家并行审查，再由总编辑汇总 | Gradio、FastAPI、规划演示 |
| MoA | 三个提议 Agent 并行生成结果，再由聚合 Agent 综合 | Gradio、FastAPI、规划演示 |
| 层级协作 | Leader 通过工具调用研究助手和审查助手 | CLI、Gradio、FastAPI |
| 圆桌共创 | 研究、审查、规划三个 Agent 通过 `MsgHub` 多轮讨论 | CLI、Gradio、FastAPI |
| 外部反馈 | 对含代码的课程内容进行反馈，并支持代码执行验证流程 | Gradio、FastAPI、规划演示 |
| Skill | 从 `SKILL.md` 加载课程审查流程 | 所有注册 Skill 的工具入口 |
| 评测 | 执行 `data/eval_cases.json` 中的用例并保存结果 | 评测脚本 |

## 架构

```text
CLI / Gradio / FastAPI + frontend/index.html
                                        |
                +-----------+-----------+
                |                       |
    工作流编排                 AgentScope
    ReAct / Planning           Agent / Toolkit
    Parallel / MoA             Pipeline / MsgHub
    Hierarchical / Co-creation PlanNotebook
                |                       |
                +-----------+-----------+
                                        |
             MCP 工具 + Skill + Memory + Evaluation
```

工具连接策略如下：

1. FastAPI 和 Gradio 优先连接配置中的远程 Streamable HTTP MCP 服务。
2. 远程服务连接失败时，回退到 `mcp_servers/web_search_server.py` 的本地 stdio MCP 服务。
3. 本地 MCP 服务是用于开发和评测的模拟搜索服务，不提供真实互联网搜索。
4. `skills/course-review/SKILL.md` 会作为 AgentScope Skill 注册，当前默认 Skill 是课程审查。

## 环境要求

- Python 3.10 或更高版本
- 一个可用的 DashScope API Key
- 运行 Web UI 时需要额外安装 `gradio`
- 运行 FastAPI 服务时需要 `fastapi` 和 `uvicorn`（它们已包含在 `requirements.txt`）

## 安装与配置

```bash
conda create -n agent_learn python=3.10
conda activate agent_learn
pip install -r requirements.txt
```

Gradio 不在当前依赖清单中，使用 Gradio 界面时补充安装：

```bash
pip install gradio
```

复制环境变量模板并填写 API Key：

```bash
# macOS / Linux / Git Bash
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

至少配置：

```dotenv
DASHSCOPE_API_KEY=你的_DashScope_API_Key
```

常用配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_MODEL` | `qwen-plus` | DashScope 对话模型 |
| `MAX_REACT_ITERS` | `10` | ReAct 最大循环次数 |
| `TEMPERATURE` | `0.0` | 模型温度 |
| `MCP_TRANSPORT` | `stdio` | CLI 使用的 MCP 传输方式，可选 `stdio` 或 `streamable_http` |
| `MCP_SERVER_URL` | DashScope WebSearch MCP 地址 | 远程 MCP 地址 |
| `ENABLE_LONG_TERM_MEMORY` | `false` | 是否启用 Mem0 + Qdrant 长期记忆 |
| `QDRANT_PATH` | `./data/memory/qdrant` | Qdrant 本地数据路径 |
| `EMBEDDING_MODEL` | `text-embedding-v4` | 长期记忆嵌入模型 |
| `EMBEDDING_DIM` | `2048` | 嵌入向量维度 |

项目实际运行时主要读取 `.env` 和环境变量。`configs/agent_config.yaml` 是配置示例，目前不会被所有入口自动加载。

## 使用方式

### 1. CLI 交互

```bash
# 默认进入 ReAct 多轮对话
python scripts/run_agent.py -i -m react

# 层级协作
python scripts/run_agent.py -i -m hierarchical

# 圆桌共创
python scripts/run_agent.py -i -m cocreation
```

也可以直接执行一次提问：

```bash
python scripts/run_agent.py -q "帮我搜集 Transformer 的教学资料" -m react
```

输入 `quit` 或 `exit` 退出交互模式。

### 2. Gradio 界面

```bash
python scripts/run_web.py
```

打开 <http://127.0.0.1:7860>，可在界面中切换以下工作流：

`ReAct Agent`、`Planning Notebook`、`Parallel Review`、`Hierarchical`、`Co-creation`、`MoA`、`External Feedback`。

### 3. FastAPI + 原生前端

```bash
python scripts/run_server.py
```

打开 <http://127.0.0.1:8000>。服务提供：

```text
GET  /health
POST /api/chat
GET  /
```

请求示例：

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
    -H "Content-Type: application/json" \
    -d '{"message":"找到 Attention Is All You Need 这篇论文","workflow":"react"}'
```

`workflow` 可选值：`react`、`planning`、`parallel`、`moa`、`hierarchical`、`cocreation`、`feedback`。

### 4. 规划能力演示

运行所有规划演示（包含多个模型调用）：

```bash
python scripts/run_planning.py --all
```

演示包括自我审查、外部反馈、Pipeline、Branching、Parallel、MoA、HITL、PlanNotebook 和动态工具创建。HITL 演示需要人工输入，因此自动流程会跳过它。

## 评测

评测用例位于 `data/eval_cases.json`，执行结果默认写入 `data/eval_result.json`：

```bash
python scripts/run_eval.py --all
```

当前用例覆盖 MCP 搜索、PlanNotebook 规划和带代码的外部反馈。评测依赖真实模型调用，请提前配置 `DASHSCOPE_API_KEY`。

## 项目结构

```text
Agent/
├── configs/
│   └── agent_config.yaml       # 配置示例
├── data/
│   ├── eval_cases.json         # 评测用例
│   ├── eval_result.json        # 评测输出
│   └── memory/qdrant/          # 本地向量存储目录
├── frontend/
│   └── index.html              # FastAPI 静态前端
├── mcp_servers/
│   └── web_search_server.py    # 本地模拟 WebSearch MCP Server
├── scripts/
│   ├── run_agent.py            # CLI
│   ├── run_server.py           # FastAPI 服务
│   ├── run_web.py              # Gradio 界面
│   ├── run_planning.py         # 规划演示
│   ├── run_eval.py             # 自动化评测
│   └── test_modules.py         # 模块测试脚本
├── skills/
│   └── course-review/SKILL.md  # 课程审查 Skill
├── src/
│   ├── agent_engine/           # Agent 创建与统一系统
# Agent 智能教学助手

基于 [AgentScope](https://github.com/modelscope/agentscope) 的智能体实验项目，面向课程资料搜集、教学文档审查和复杂任务编排。项目把 ReAct、MCP、Skill、规划、记忆、多智能体协作和自动评测放在同一套可运行代码中，适合学习和验证 Agent 工作流设计。

> 当前项目依赖 DashScope API。仓库内置的本地 MCP 服务是用于开发调试的模拟搜索服务，不提供真实互联网搜索。

## 功能概览

### 工作流

| 工作流 | 实现位置 | 说明 |
| --- | --- | --- |
| ReAct Agent | `src/agent_engine/react_agent.py` | 思考、工具调用、观察和回答的循环 |
| Planning Notebook | `src/planning/plan_notebook.py` | 创建计划、执行子任务并完成计划 |
| Pipeline | `src/planning/workflow.py` | 代码提取、验证、报告生成的顺序流水线 |
| Branching | `src/planning/workflow.py` | 根据请求选择代码检查、润色或完整评审分支 |
| Parallel Review | `src/planning/workflow.py` | 代码、事实、教学法和风格四类专家并行审查 |
| MoA | `src/planning/workflow.py` | 多个提议 Agent 并行生成结果，再由聚合器汇总 |
| Hierarchical | `src/orchestration/hierarchical.py` | Leader 调度研究助手和审查助手 |
| Co-creation | `src/orchestration/cocreation.py` | 多个 Agent 通过 MsgHub 多轮讨论并总结 |
| External Feedback | `src/planning/reflection.py` | 润色文本，并使用外部反馈验证其中的代码 |
| HITL | `src/planning/workflow.py` | 在需要时通过工具请求人工决策 |

### 共享能力

- **工具**：通过 MCP 注册工具；通过 `skills/*/SKILL.md` 注册标准化流程；支持动态工具创建。
- **MCP**：支持本地 stdio 服务和 DashScope Streamable HTTP 服务。Web/FastAPI 入口优先尝试远程服务，再回退本地服务。
- **记忆**：默认使用 AgentScope 的短期内存；可选 Mem0 + Qdrant 长期记忆。
- **评测**：`data/eval_cases.json` 提供用例，评测结果写入 `data/eval_result.json`。
- **界面**：提供 Gradio 界面，以及 FastAPI + 原生 HTML 前端两种 Web 入口。

## 环境要求

- Python 3.10 或更高版本
- 可用的 DashScope API Key
- 本地 MCP 模式需要 Python 能够启动 `mcp_servers/web_search_server.py`

## 安装与配置

```bash
conda create -n agent_learn python=3.10
conda activate agent_learn
pip install -r requirements.txt
```

复制环境变量模板并填写 API Key：

```bash
copy .env.example .env       # Windows PowerShell
# cp .env.example .env       # macOS/Linux
```

至少配置：

```dotenv
DASHSCOPE_API_KEY=你的_DashScope_API_Key
```

常用环境变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DASHSCOPE_API_KEY` | 无 | DashScope 模型和远程 MCP 鉴权 |
| `LLM_MODEL` | `qwen-plus` | 使用的聊天模型 |
| `MAX_REACT_ITERS` | `10` | ReAct 最大循环次数 |
| `TEMPERATURE` | `0.0` | 模型温度 |
| `MCP_TRANSPORT` | `stdio` | CLI 使用的 MCP 传输方式：`stdio` 或 `streamable_http` |
| `MCP_SERVER_URL` | DashScope WebSearch MCP 地址 | 远程 MCP 地址 |
| `ENABLE_LONG_TERM_MEMORY` | `false` | 是否启用 Mem0 + Qdrant 长期记忆 |
| `QDRANT_PATH` | `./data/memory/qdrant` | Qdrant 本地数据路径 |

`configs/agent_config.yaml` 保存了较完整的示例配置，但当前 Python 入口的实际配置主要由 `.env` 和 `src/config.py` 读取。

## 运行方式

### CLI

交互式对话：

```bash
python scripts/run_agent.py --interactive --mode react
python scripts/run_agent.py --interactive --mode hierarchical
python scripts/run_agent.py --interactive --mode cocreation
```

单次提问：

```bash
python scripts/run_agent.py --question "帮我搜集 Transformer 的教学资料" --mode react
python scripts/run_agent.py -q "审查这份课程内容" -m hierarchical
```

CLI 当前支持 `react`、`hierarchical`、`cocreation` 三种模式。输入 `quit` 或 `exit` 可退出交互模式。

### Gradio 界面

```bash
python scripts/run_web.py
```

打开 <http://127.0.0.1:7860>，可在界面中选择 ReAct、Planning Notebook、Parallel Review、MoA、Hierarchical、Co-creation 和 External Feedback。

### FastAPI + 原生前端

```bash
python scripts/run_server.py
```

打开 <http://127.0.0.1:8000>。前端通过 `/api/chat` 调用后端，健康检查地址为 `/health`。

请求示例：

```bash
curl -X POST http://127.0.0.1:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"找到 Attention Is All You Need 这篇论文\",\"workflow\":\"react\"}"
```

`workflow` 支持：`react`、`planning`、`parallel`、`moa`、`hierarchical`、`cocreation`、`feedback`。

### 规划能力演示

运行所有规划示例会连续调用多个模型工作流，消耗较多 API 调用：

```bash
python scripts/run_planning.py --all
```

### 本地 MCP 服务

通常不需要单独启动，CLI 和 Web 入口会按需启动 `mcp_servers/web_search_server.py`。如需单独调试：

```bash
python scripts/run_mcp_server.py
```

本地服务中的 `web_search` 根据内置数据返回模拟结果，包含 Transformer、BERT 和大型语言模型等示例关键词。

## 自动评测

评测用例位于 `data/eval_cases.json`，包括工具调用、规划和代码反馈场景：

```bash
python scripts/run_eval.py --all
```

评测结果会保存到 `data/eval_result.json`。评测依赖模型调用，运行前请确认 API Key 和 MCP 服务可用。

## 项目结构

```text
Agent/
├── configs/                  # YAML 示例配置
├── data/                     # 评测用例、结果和本地记忆数据
├── frontend/                 # FastAPI 使用的原生 HTML 前端
├── mcp_servers/              # 本地 MCP 服务
├── scripts/                  # CLI、Web、服务端、规划和评测入口
├── skills/                   # SKILL.md 技能定义
└── src/
    ├── agent_engine/         # ReAct Agent 和统一 Agent 系统
    ├── api/                  # FastAPI 路由与 Pydantic 模型
    ├── evaluation/           # 自动评测
    ├── memory/               # 短期和长期记忆
    ├── orchestration/        # Hierarchical 和 Co-creation
    ├── planning/             # 规划、反思、工作流和动态工具
    ├── skills/               # Skill 加载器
    └── tools/                # MCP 和 Skill 工具注册
```

## 开发提示

- 修改模型、MCP 或记忆配置时，优先检查 `.env` 和 `src/config.py`。
- 长期记忆默认关闭；启用后需要确认 `mem0ai`、Qdrant 本地目录和 embedding 配置可用。
- 多智能体工作流会并行或顺序创建多个模型调用，成本和耗时高于单 Agent。
- `scripts/run_planning.py --all` 包含 HITL 能力说明，但 HITL 演示会跳过实际人工输入。
- 本地模拟搜索适合开发调试；生产或真实检索场景应配置可用的远程 MCP 服务。

## 学习资料

项目内容参考 [阿里云大模型 ACP 认证课程](https://edu.aliyun.com/course/3130200)，涉及 RAG、Agent 设计开发、模型优化与上线等主题。
