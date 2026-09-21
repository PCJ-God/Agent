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

两种用法：**匿名**（打开即用，什么都不用填）和**具名**（用户名 + 密码，可跨设备）。

```bash
# 1. 匿名：直接拿一个 token
curl -X POST http://127.0.0.1:8000/api/auth/register \
     -H "Content-Type: application/json" -d '{"name":""}'
# → {"user_id":"...","token":"...","name":"","created_at":"...",
#    "username":null,"is_anonymous":true}

# 2. 具名：注册时就带上用户名密码（也可以先匿名，之后再把凭据绑上去）
curl -X POST http://127.0.0.1:8000/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username":"alice","password":"at-least-8-chars"}'

# 3. 之后所有请求带上 token
curl http://127.0.0.1:8000/api/sessions -H "Authorization: Bearer <token>"
```

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 不带 `username`/`password` → 匿名账号；带了 → 具名账号（重名 409） |
| `POST` | `/api/auth/login` | 用户名 + 密码换一个**新** token（支持多设备并存） |
| `POST` | `/api/auth/bind` | 给**当前匿名账号**补上用户名密码，已有历史原地保留 |
| `POST` | `/api/auth/logout` | 吊销**当前** token（其他设备不受影响，账号和历史都还在） |
| `GET` | `/api/auth/me` | 校验 token，返回当前用户（含 `username` / `is_anonymous`） |

密码用标准库 `hashlib.scrypt` 哈希（内存硬，不引入新依赖），存储格式自描述，
将来换算法只需按前缀分派校验逻辑。用户名不区分大小写；登录失败按用户名做
窗口限流（见 `server.py` 的 `_LOGIN_WINDOW` / `_LOGIN_MAX_FAILS`）。

**为什么要「绑定凭据」而不是「新建账号」**：`user_id` 是数据归属的唯一依据
（会话、消息、长期记忆都按它隔离），所以注册的本质是给当前这个 `user_id`
补一组「能再次证明身份」的凭据 —— 历史不用搬，天然就在原地。

token 仍是「一票通行」的凭证：**只在 HTTPS 下暴露**，要吊销用
`POST /api/auth/logout`（`session_store.revoke_token`）。

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
- **网页端**：首次打开自动建一个匿名账号并存下 token（打开即用，不用填任何东西）；顶栏「账号」按钮可以设置用户名密码（之后在别的设备登录能看到同一份历史）、退出登录或用另一个账号登录；「任务」下拉框切换任务、「新建任务」开新任务；向上滚动自动加载更早的历史

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