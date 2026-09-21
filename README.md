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
| `LTM_SCOPE` | `session` | 长期记忆作用域: `session` 会话间隔离 / `global` 跨会话累积 |

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

## 用户、会话（任务）与记忆

两层隔离：**用户** 和 **任务**。一个用户可以有多个任务，任务之间完全隔离；
不同用户之间在任何层面都不共享东西。

| 层面 | 隔离方式 |
|------|----------|
| 用户 | `users` 表 + uuid token；除 `/health` 外所有接口都要 `Authorization: Bearer <token>` |
| 短期记忆 | 每个 (用户, 任务) 一个 `HierarchicalTeam`，各自一份 `InMemoryMemory` |
| 长期记忆 | user_id → Mem0 的 `user_id`，任务 ID → `run_id`（`LTM_SCOPE=session` 时），两者都是检索过滤条件 |
| 对话历史 | 按 (user_id, session_id) 存进 SQLite（`data/sessions.db`），进程重启也不丢 |
| 并发 | 锁按 (用户, 任务) 分 —— 都能并行推进，只在同一任务内串行 |

重新打开一个任务时，会把它最近 `HISTORY_REPLAY_TURNS` 轮对话回放进 Leader 的记忆，
所以它是「接着聊」；历史也可以在界面上分页往前翻。

### 认证

```bash
# 1. 注册，拿 token（uuid4）
curl -X POST http://127.0.0.1:8000/api/auth/register \
     -H "Content-Type: application/json" -d '{"name":""}'
# → {"user_id":"...","token":"...","name":"","created_at":"..."}

# 2. 之后所有请求带上它
curl http://127.0.0.1:8000/api/sessions -H "Authorization: Bearer <token>"
```

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 发一个 uuid token |
| `GET` | `/api/auth/me` | 校验 token，返回当前用户 |

token 相当于「用户名 + 密码」合一：**只在 HTTPS 下暴露**，吊销用
`session_store.revoke_token(token)`。将来接真正的登录体系时，只需替换
`src/access/auth.py` 里的 `current_user`，下游一行都不用改。

### 任务接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/sessions` | 列出**当前用户**的任务（最近活跃的在前） |
| `POST` | `/api/sessions` | 新建任务，body 可带 `session_id` / `title` |
| `DELETE` | `/api/sessions/{id}` | 删除任务及其历史 |
| `GET` | `/api/sessions/{id}/messages?limit=20&before=<游标>` | 分页读取对话历史 |

`messages` 按时间正序返回；`next_cursor` 是下次往前翻要传的 `before`，为 `null` 表示已经到头。

### 资源隔离（公网必看）

| 配置 | 默认 | 作用 |
|------|------|------|
| `QDRANT_URL` | 空 | **线上必须设** —— 本地文件版是单进程独占的，多 worker 会抢锁失败 |
| `MAX_SESSIONS_PER_USER` | 50 | 每人任务数上限，超出返回 429 |
| `MAX_TEAMS` | 20 | 进程内保留的任务实例上限，超出按 LRU 淘汰空闲的（历史仍在 SQLite，下次访问重建） |
| `RATE_LIMIT_PER_MINUTE` | 20 | 每人每分钟对话请求上限，超出返回 429 |

### 怎么用

- **CLI**：`python scripts/run_agent.py -i --session taskA --user alice`（默认 `cli-default` / `local`）
- **HTTP**：带 `Authorization` 头，请求体里带 `session_id`
- **网页端**：首次打开自动注册并存下 token；顶栏「任务」下拉框切换、「新建任务」开新任务；向上滚动自动加载更早的历史

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