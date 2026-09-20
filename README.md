# Agent 智能教学助手 — 层级协作模式

基于 [AgentScope](https://github.com/modelscope/agentscope) 的多 Agent 层级协作系统，采用四层架构设计。

> 当前项目依赖 DashScope API 与远程 MCP（DashScope 联网搜索）。

## 四层架构

```
┌─────────────┐
│  接入层      │  CLI / FastAPI — 处理用户输入
├─────────────┤
│  调度层      │  Leader Agent — 任务拆解、优先级排序、调度
├─────────────┤
│  执行层      │  Researcher + Reviewer + MCP 工具 + Skill
├─────────────┤
│  存储层      │  Mem0/Qdrant 长期记忆
└─────────────┘
```

| 层级 | 位置 | 职责 |
|------|------|------|
| 接入层 | `src/access/` | CLI 交互、FastAPI REST API、Web 前端 |
| 调度层 | `src/orchestration/` | Leader 拆解任务、分配优先级、协调执行 |
| 执行层 | `src/execution/` | ReAct Agent、MCP 工具注册、Skill 加载 |
| 存储层 | `src/storage/` | 向量化长期记忆 (Mem0+Qdrant) |

## 环境要求

- Python 3.10+
- DashScope API Key

## 安装与配置

```bash
conda create -n agent_learn python=3.10
conda activate agent_learn
pip install -r requirements.txt
```

复制环境变量模板并填写 API Key：

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
```

至少配置：

```dotenv
DASHSCOPE_API_KEY=你的_DashScope_API_Key
```

常用环境变量：

| 变量 | 默认值 | 用途 |
|------|--------|------|
| `DASHSCOPE_API_KEY` | 无 | DashScope 模型和远程 MCP 鉴权 |
| `LLM_MODEL` | `qwen-plus` | 使用的聊天模型 |
| `MAX_REACT_ITERS` | `10` | ReAct 最大循环次数 |
| `MCP_SERVER_URL` | DashScope WebSearch | 远程 MCP 服务地址 |
| `ENABLE_LONG_TERM_MEMORY` | `true` | 是否启用 Mem0 + Qdrant 长期记忆 |

## 运行方式

### CLI 交互式对话

```bash
python scripts/run_agent.py --interactive
```

### CLI 单次提问

```bash
python scripts/run_agent.py --question "帮我搜集 Transformer 的教学资料"
```

输入 `quit` 或 `exit` 退出交互模式。

### FastAPI + 前端

```bash
python scripts/run_server.py
```

打开 <http://127.0.0.1:8000>。

请求示例：

```bash
curl -X POST http://127.0.0.1:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"找到 Attention Is All You Need 这篇论文\"}"
```

## 项目结构

```text
Agent/
├── frontend/                 # 原生 HTML 前端
├── scripts/                  # CLI、Server 入口
├── skills/                   # SKILL.md 技能定义
└── src/
    ├── config.py             # 全局配置 + 日志
    ├── access/               # 接入层
    │   ├── cli.py            # CLI 核心逻辑
    │   └── server.py         # FastAPI 核心逻辑
    ├── orchestration/        # 调度层
    │   └── hierarchical.py   # Leader-Worker 层级调度
    ├── execution/            # 执行层
    │   ├── agents/           # ReAct Agent + 工厂
    │   └── tools/            # MCP 工具池 + Skill 分发
    └── storage/              # 存储层
        └── memory/           # 长期记忆 (Mem0 + Qdrant)
```

## 工作流说明

系统只保留 **层级协作 (Hierarchical)** 模式：

1. **Leader (调度层)** 接收用户请求，拆解为子任务
2. **Researcher (执行层)** 搜集整理资料
3. **Reviewer (执行层)** 审查质量并给出改进建议
4. Leader 汇总结果，交付最终输出

## 学习资料

项目内容参考 [阿里云大模型 ACP 认证课程](https://edu.aliyun.com/course/3130200)。