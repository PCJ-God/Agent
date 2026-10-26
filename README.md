# 🎓 ACP Copilot: 专为阿里云认证打造的学习助手

## 📖 项目简介 (Introduction)

本项目是一个基于大语言模型（LLM）与多智能体（Agent）架构的垂直领域学习助手。专为备考**阿里云 ACP 认证（云计算专业认证）**的学生设计。系统结合了本地私有知识库（RAG）与联网搜索兜底机制，并具备长短期记忆分离能力，能够像真实助教一样提供精准、及时、个性化的辅导。

## ⚡ 快速启动 (Quick Start)

### 0. 前置要求

- Docker Desktop（含 Docker Compose v2）
- 阿里云百炼平台的 [DashScope API Key](https://bailian.console.aliyun.com/)（模型调用 + 联网搜索 MCP 鉴权必需）

### 1. 配置环境变量

```bash
cp .env.example .env    # Windows: copy .env.example .env
```

编辑 `.env`，至少填入：

```ini
DASHSCOPE_API_KEY=sk-你的真实Key
```

> `DASHSCOPE_API_KEY` 是唯一必填项，未设置时 `docker compose up` 会直接报错退出；其余变量（模型名、各类密码）均有默认值，可先不修改。

### 2. 一键启动

```bash
docker compose up -d --build
```

- 首次启动会构建 `gateway` / `ai-engine` 两个自建镜像并拉取基础设施镜像，约需数分钟。
- 前端为 Vue 构建产物，仓库已含 `frontend/dist`；改动前端源码后重新构建：`cd frontend && npm install && npm run build`。
- 之后日常启动/重启用 `docker compose up -d` 即可。

### 3. 检查状态

```bash
docker compose ps                       # 12 个容器应全部 Up（mysql/rabbitmq/redis 为 healthy）
curl http://localhost:8080/health       # 网关健康检查，返回 {"status":"ok"}
```

浏览器打开 **http://localhost:8081** 即进入前端界面（登录后可对话、检索、上传文档）。

### 4. 冒烟验证（可选）

```bash
pwsh scripts/phase1_smoke.ps1           # 注册/登录/带 JWT 查 /me 全链路（需 PowerShell 7+）
```

`phase2` ~ `phase6` 分别验证对话、RAG、Agent、记忆、异步文档解析链路，可依次执行。

### 端口速查

| 服务 | 地址 | 账号 | 说明 |
| :--- | :--- | :--- | :--- |
| Nginx（前端 + API 入口） | http://localhost:8081 | — | 静态托管前端 + 反代 /api |
| 网关 Gateway | http://localhost:8080 | — | 调试直连，携带 JWT |
| AI 引擎 | http://localhost:8000 | — | 内部服务，一般不直连 |
| Prometheus | http://localhost:9090 | — | 指标抓取 |
| Grafana | http://localhost:3000 | admin / admin | 监控面板 |
| RabbitMQ 管理台 | http://localhost:15672 | acp / acp | 队列观测 |
| MinIO 控制台 | http://localhost:9001 | acpadmin / acpadmin123 | 对象存储 |

### 停止与清理

```bash
docker compose down        # 停止并移除容器（保留数据卷）
docker compose down -v     # 连同数据卷一并删除（清空 MySQL/Redis/向量库等）
```

## 🎯 核心痛点与解决方案 (Pain Points & Solutions)

1. **知识更新极快，本地库易过时**
   * **方案**：采用 **Agentic RAG** 架构。优先检索本地 ACP 官方文档（Chroma 向量库）；若本地未命中，Agent 自动触发 **Function Calling** 调用联网搜索工具（DashScope MCP 的 `bailian_web_search`），获取最新网页信息，保证回答的时效性。
2. **大模型缺乏记忆，无法因材施教**
   * **方案**：长短记忆分离机制。
     * **短期记忆**：基于 Redis List 的**滑动窗口**，利用 LLM 对早期对话进行**摘要压缩（Summary Memory）**，解决上下文窗口（Context Window）爆炸和截断失忆问题。
     * **长期记忆**：基于 Mem0 中间件，跨会话自动提炼并向量化存储用户画像（如：零基础、易错点、目标考试时间）。
3. **提问形式单一，交互体验差**
   * **方案**：支持多模态附件上传。图片/PDF/日志文件存入 OSS/MinIO 对象存储，数据库仅存 URL 和元数据，并在前端与消息流绑定渲染。

---

## 🏗️ 系统架构设计 (Architecture)

系统采用 **“Go 业务底座 + Python AI 引擎”** 的混合微服务架构，实现算力隔离与高并发解耦：

```text
[前端 (Vue/React/小程序)]
   │  (HTTP/SSE流式返回, 携带 JWT 和 附件URL)
   ▼
[接入层 (Go - Gin)] ─── (Redis 限流 / JWT 鉴权 / 附件存储 MinIO)
   │
   ▼  (gRPC / HTTP)
[业务与持久化层 (Go)] 
   ├── 业务逻辑：MySQL (User, Session, Message, Agent, Attachment)
   ├── 快速缓存：Redis (接口限流、Token配额)
   └── 消息队列：RabbitMQ (异步文档解析、记忆摘要)
   │
   ▼  (HTTP)
[AI 引擎层 (Python - AgentScope)]
   ├── RAG 引擎：Chroma (ACP 文档向量检索) + LlamaIndex 管线
   ├── 工具生态：Web Search Tool (DashScope MCP 联网兜底)
   ├── 短期记忆：RedisMemory (滑动窗口 + 摘要压缩)
   └── 长期记忆：Mem0 (自动提炼用户画像，向量存 Qdrant)
```

**为什么消息队列选 RabbitMQ 而不是 Kafka**：本项目的异步负载是「文档解析 / 记忆摘要」这类低频任务队列——要求可靠投递、失败重试、死信队列，而非 Kafka 擅长的高吞吐事件流。RabbitMQ 更轻、更对口；Redis 仅承担缓存 / 限流 / 短期记忆，不兼任队列。

## 🔍 RAG 检索管线设计 (RAG Pipeline)

RAG 是「本地知识库 + 联网兜底」中本地检索的核心，采用 7 环节管线：

```text
文档摄入 → 索引 → 检索 → 生成 → 记忆 → 安全护栏 → 评测
```

| 环节 | 模块职责 | 关键设计 |
| :--- | :--- | :--- |
| 文档摄入 | 加载 ACP 官方 Markdown，结构感知分块 | 按标题层级切块，写入 `header_path` 溯源元数据 |
| 索引 | 向量化并写入 Chroma | Embedding 抽象，后端可切换 |
| 检索 | 意图识别 → 改写/指代消解 → 拆解 → 混合召回 → 重排 | 语义 + 标签两路召回，两阶段检索（qwen3-rerank 精排） |
| 生成 | 拼上下文 → 调 LLM → 带引用回答 | 强制只用资料回答，引用编号可溯源 |
| 记忆 | 多轮对话记忆（改写、指代消解） | 滑动窗口 + 语义召回 |
| 安全护栏 | 输入/输出双向内容审核 | fail-open 保证主链路可用 |
| 评测 | Ragas 跑 QA 对 | 忠实度 / 正确性 / 召回率 / 精确率 |

两条质量红线（来自真实踩坑经验）：

1. **引用程序化校验**：生成时返回「编号 → 文档块」映射，生成后校验回答里的 `[i]` 是否属于本次实际注入的块，越界判不可信，不靠 prompt 许愿。
2. **结构感知分块要实测**：切片后必须验证每块的 `header_path` 元数据真的存在，避免「溯源字段形同虚设」。

**与 Agent 的集成方式**：整条 RAG 管线作为自包含模块，以**工具**形式暴露给 AgentScope Agent——Agent 判断是「知识题」时调 RAG 工具（本地 Chroma 检索，带引用），本地未命中或知识过时时调 MCP 联网搜索，这正是「Agentic RAG」的实现路径。

## 🧠 记忆机制深度设计 (Memory Design)

为了平衡大模型的“算力成本”与“记忆连贯性”，我们设计了如下机制：

* **短期记忆（RedisMemory）**：
    * 按 `session_id` 隔离，数据按 JSON 格式存在 Redis List 中。
    * **滑动窗口**：仅保留最近 N 轮对话。
    * **摘要压缩**：当 Token 超出阈值，后台通过 RabbitMQ 异步拉起任务，将最早的 10 条消息交由 LLM 生成摘要，用摘要替换原文，节省 Token。
* **长期记忆（Mem0）**：
    * 采用 `Mem0Middleware` 中间件形式挂载。
    * 利用复用的 LLM 自动抽取对话中关于用户的“事实与偏好”。
    * 在 `on_reply` 钩子中自动检索（注入 Prompt）与写回（存入向量库）。

## 🗄️ 数据库与存储设计 (Storage)

本系统严格遵循**“各司其职”**的存储原则，拒绝把 MySQL 当垃圾桶：

| 组件 | 存储内容 | 职责说明 |
| :--- | :--- | :--- |
| **MySQL** | `User`, `Agent`, `Session`, `Message`, `Attachment` | 核心业务元数据，关系型强一致性存储（GORM 软删除、索引） |
| **Redis** | 短期记忆、JWT黑名单、限流计数器 | 极高并发读写缓存（无状态下的快速状态共享） |
| **RabbitMQ** | 异步任务队列（文档解析、记忆摘要） | 可靠投递（ack + 重试 + 死信队列），削峰填谷、系统解耦 |
| **OSS/MinIO** | 用户上传的图片、PDF附件文件 | 物理大文件存储（MySQL仅存文件URL） |
| **Chroma** | 本地 ACP 文档切片 | RAG 语义检索（高维向量数据） |
| **Qdrant** | Mem0 提取的长期记忆 | 用户画像语义检索 |

*注：核心业务表结构已预留 `source`（回答来源：local/web/mixed）和 `search_query`（联网搜索词）字段，方便后续做模型评测与数据追踪。*

## 🛠️ 技术栈 (Tech Stack)

* **后端基座**：Go (Gin, GORM), gRPC
* **AI 引擎**：Python (FastAPI), AgentScope (ReAct 规划), LlamaIndex (RAG 管线), Mem0
* **数据存储**：MySQL, Redis, RabbitMQ, Chroma, Qdrant
* **大模型接入**：阿里云通义千问 (Qwen) / 智谱 GLM
* **工程化与运维**：Docker Compose, MinIO, Prometheus, Grafana

## 🚀 开发路线图 (Roadmap)

- [ ] **Phase 1: 基础架构搭建** (Go + Gin + MySQL + JWT + FastAPI)
- [ ] **Phase 2: 纯文本对话链路跑通** (Python 接入通义千问)
- [ ] **Phase 3: RAG 知识库检索** (Chroma + 文档摄入/索引/检索管线)
- [ ] **Phase 4: Agent 引入与工具调用** (AgentScope + RAG 工具 + Web Search 兜底)
- [ ] **Phase 5: 记忆机制深度集成** (RedisMemory + Mem0 Middleware)
- [ ] **Phase 6: 异步与文件处理** (RabbitMQ 异步解析文档 + OSS/MinIO)
- [ ] **Phase 7: 工程化与监控** (Docker Compose 部署 + Prometheus 监控埋点)
