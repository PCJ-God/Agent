# ACP Copilot — 阿里云认证学习助手

面向阿里云 ACP（云计算专业认证）备考的垂直领域 AI 学习助手。系统采用「Go 业务底座 + Python Agent 引擎」的混合架构，结合本地课程知识库（RAG）与联网搜索兜底，并具备长短期记忆分离能力，提供精准、可溯源的个性化辅导。

## 功能特性

- **Agentic RAG**：AgentScope `ReActAgent` 自主决定检索本地课程库（LlamaIndex + Qdrant）还是联网搜索兜底（DashScope MCP），回答带 `[编号]` 引用。
- **长短期记忆分离**：短期记忆会话内保留、新会话自动清空；长期记忆用 mem0 跨会话积累用户画像（零基础、易错点、备考目标等）。
- **多模态附件**：支持 PDF / Word / 图片 / 文本上传，解析后注入对话上下文（Web 与飞书均可发图）。
- **Markdown 渲染 + 代码高亮**：助手回复按 Markdown 渲染（标题 / 列表 / 表格 / 代码块），代码块经 highlight.js 语法高亮，DOMPurify 清洗防 XSS。
- **管理员知识库管理**：一键重灌课程库、上传文档异步入库。
- **可观测**：Prometheus 指标 + Grafana 面板，网关与 AI 引擎均暴露 `/metrics`。
- **飞书机器人**：@机器人 提问，回答以 **CardKit 流式卡片**逐字呈现（typewriter），支持发图片；需先在 Web 端绑定飞书账号（验证码），账号与长期记忆与 Web 端共用。

## 系统架构

```text
浏览器（Vue 3，:8081）
   │  HTTP / SSE（/api/*，携带 JWT）
   ▼
nginx（静态托管 + 反代）
   │
   ▼
gateway（Go · Gin）
   ├─ JWT 鉴权 / 每日限流 / 登出黑名单（Redis）
   ├─ 附件元数据（MySQL）+ 附件实体（MinIO）
   │
   │  gRPC（:50051）
   ▼
ai-engine（Python · FastAPI + AgentScope ReActAgent）
   ├─ search_course ── LlamaIndex + Qdrant（acp_docs 课程库）
   ├─ web_search   ── DashScope 远程 MCP（bailian_web_search）
   ├─ 短期记忆      ── 进程内（会话内保留）
   └─ 长期记忆      ── mem0 + Qdrant（mem0 集合）
   │
   ▼  RabbitMQ doc_parse 队列
ai-worker（异步文档解析：docx / pdf / OCR → gRPC IngestText 写回课程库）

飞书用户 ──长连接──▶ feishu-adapter（绑定 Web 账号后以网关签发的 JWT 调 /api/assistant；
                    CardKit 流式卡片 + 图片）

基础设施：MySQL / Redis / RabbitMQ / Qdrant / MinIO / Prometheus + Grafana
```

## 快速开始

### 0. 前置要求

- Docker Desktop（含 Docker Compose v2）
- 阿里云百炼 [DashScope API Key](https://bailian.console.aliyun.com/)（模型调用 + 联网搜索 MCP 鉴权必需）

### 1. 配置环境变量

```bash
copy .env.example .env     # Linux/macOS: cp .env.example .env
```

编辑 `.env`，填入：

```ini
DASHSCOPE_API_KEY=sk-你的真实Key
```

`DASHSCOPE_API_KEY` 是唯一必填项，未设置时 `docker compose up` 会直接报错。其余变量（模型名、各类口令、限流额度）均有默认值，可先不改。

### 2. 启动

```bash
docker compose up -d --build
```

- 首次构建 `gateway` / `ai-engine` / `feishu-adapter` 自建镜像并拉取基础设施镜像，约需数分钟。
- 前端为 Vue 构建产物：首次部署需执行 `cd frontend && npm install && npm run build` 生成 `frontend/dist`（该目录不进版本控制，nginx 直接托管）；改动前端源码后重新 build 即可。
- 日常启停用 `docker compose up -d` / `docker compose down` 即可。

### 3. 验证

```bash
docker compose ps                    # 12 个容器应全部 Up（mysql/rabbitmq/redis 为 healthy）
curl http://127.0.0.1:8080/health   # 网关健康检查，返回 {"service":"gateway","status":"ok"}
```

浏览器打开 http://localhost:8081 进入前端（命令行验证请用 `127.0.0.1`，见下）。

> **Windows 注意**：Docker Desktop 重启后 `localhost` 可能先解析到 IPv6 `::1` 导致端口转发未就绪；浏览器会自动回退 IPv4 不受影响，命令行请统一用 `127.0.0.1`。

### 4. 冒烟验证（可选）

登录管理员（网关首次启动自动创建，默认 `admin / admin123456`）：

```bash
curl -s -X POST http://127.0.0.1:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123456"}'
# 返回 JSON 中的 token 记为 $TOKEN
```

重灌课程知识库（清空重建 Qdrant，分块 + 向量化 `ai-engine/data/docs` 下全部文档）：

```bash
curl -s -X POST http://127.0.0.1:8080/api/admin/reindex \
  -H "Authorization: Bearer $TOKEN" -d '{}'
# 返回 {"ingested":648,"sources":[...]}
```

流式对话（SSE）：

```bash
curl -N -X POST http://127.0.0.1:8081/api/assistant \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"什么是RAG？如何优化RAG问答准确率？","session_id":"s1","task_ids":[]}'
# 依次输出 step（工具轨迹）→ delta（逐段文本）→ done
```

### 端口速查

| 服务 | 地址 | 账号 | 说明 |
| :--- | :--- | :--- | :--- |
| Nginx（前端 + API 唯一入口） | http://localhost:8081 | 应用管理员 admin/admin123456（默认） | 静态前端 + 反代 /api |
| 网关 Gateway | http://localhost:8080 | — | 调试直连，需携带 JWT |
| AI 引擎 | http://localhost:8000（HTTP）/ :50051（gRPC） | — | 内部服务，一般不外连 |
| Prometheus | http://localhost:9090 | — | 指标抓取 |
| Grafana | http://localhost:3000 | admin / admin | 监控面板 |
| RabbitMQ 管理台 | http://localhost:15672 | acp / acp | 队列观测 |
| MinIO 控制台 | http://localhost:9001 | acpadmin / acpadmin123 | 附件对象存储 |
| Qdrant | http://localhost:6333 | — | 向量库 REST |

### 停止与清理

```bash
docker compose down        # 停止并移除容器（保留数据卷）
docker compose down -v     # 连同数据卷删除（清空 MySQL/Redis/Qdrant/附件等）
```

## 生产部署（HTTPS）

本地开发用 `deploy/nginx.dev.conf`（8081 / 8443）。对外提供可信 HTTPS 时切到生产配置：

1. **切换生产配置与端口**（写入 `.env`）：

   ```ini
   NGINX_HTTP_PORT=80
   NGINX_HTTPS_PORT=443
   NGINX_CONF_PATH=./deploy/nginx.conf
   ```

   `deploy/nginx.conf`：80 端口仅放行 `/.well-known/acme-challenge/` 供 Let's Encrypt 验证、其余一律 `301` 跳转 HTTPS；443 加载 `deploy/certs/server.crt` / `server.key`。

2. **首次签发 Let's Encrypt 证书**（域名需解析到本机、80 端口对公网放行）：

   ```bash
   sudo docker compose stop nginx
   sudo docker run --rm \
     -v "$PWD/deploy/letsencrypt:/etc/letsencrypt" -p 80:80 \
     certbot/certbot certonly --standalone \
     -d your-domain.com -d www.your-domain.com \
     --email you@example.com --agree-tos --non-interactive
   sudo cp -L deploy/letsencrypt/live/your-domain.com/fullchain.pem deploy/certs/server.crt
   sudo cp -L deploy/letsencrypt/live/your-domain.com/privkey.pem  deploy/certs/server.key
   sudo docker compose up -d --force-recreate --no-deps nginx
   ```

3. **自动续期**（webroot，无需停 nginx）：`renew_cert.sh` 随仓库提供，配 cron 每日检查（未到期时 certbot 自动跳过，证书有变才重启 nginx）：

   ```bash
   crontab -e
   # 0 3 * * * /bin/bash /path/to/renew_cert.sh >> /path/to/renew.log 2>&1
   ```

   续期走 webroot：`deploy/certbot/www` 挂到 nginx 的 `/var/www/certbot`，配合 `nginx.conf` 里对 `/.well-known/acme-challenge/` 的放行，全程无需停 nginx。

> 证书与私钥（`deploy/certs`、`deploy/letsencrypt`）已在 `.gitignore`，不入库。直接用 IP 访问仍会告警（IP 不在证书 SAN 内），请用域名访问。

## 使用说明

- **对话**：登录后输入问题，回车发送。Agent 自动检索课程库，未命中或需最新信息时自动联网搜索，回答带 `[编号]` 引用。
- **附件**：对话框可上传 PDF / Word / 图片 / 文本，先入队异步解析、完成后注入上下文（超长内容会被拒收）。
- **管理员**：登录 admin 账号后出现「知识库管理」页，可一键重灌课程库、上传文档异步入库。

## 飞书接入

飞书作为独立渠道接入，复用 Web 端同一账号、AI 链路与长期记忆，不改动 AI 引擎。

- **绑定**：飞书 @机器人 发「绑定」→ 网关生成 6 位验证码（Redis，5 分钟）→ Web 端「飞书绑定」页输入 → 写入 `users.feishu_open_id`；未绑定用户会被引导去 Web 注册。
- **身份映射**：单聊 `session_id=chat_id`、`user_id=open_id`（长期记忆按人）；群聊仅 @机器人 响应。适配器用 open_id 走后端内部端点 `/api/internal/feishu/token` 换 JWT（`X-Internal-Token` 鉴权），行为与 Web 一致。
- **流式**：回答用 **CardKit v1 流式卡片**（`创建卡片实体 → 发送 → PUT 元素全文 → PATCH 关闭流式`）。适配器本地聚合正文、按 0.25s 节流推送，客户端 typewriter 平滑渲染；CardKit 不可用时自动回退整卡 patch。
- **图片**：`image` / `post` 消息 → 下载资源 → 上传网关 `/api/files/upload` → worker 视觉解析 → 注入上下文作答（与 Web 同一链路）。

**飞书应用权限**（开发者后台「权限管理」开通，**变更后必须发布应用版本才生效**）：

- `cardkit:card:write` — 流式卡片
- `im:resource` — 读取消息中的图片资源
- （接收 / 发送消息所需权限应用此前已具备）

## 核心机制

### Agentic RAG

RAG 是自包含模块（`ai-engine/app/rag.py`），以 `search_course` 工具的形式暴露给 Agent：

- **摄入**：`ingest_docs` 清空重建——按 Markdown 标题层级切块（写入 `header_path` 溯源元数据）→ DashScope `text-embedding-v4` 分批嵌入 → 写入 Qdrant（`acp_docs`）；`ingest_text` 追加单篇（worker / 管理员入库用）。
- **检索**：向量召回 Top12 + BM25（jieba 分词）Top12 → RRF 倒数排名融合 → 可选 `gte-rerank` 精排 → 返回带 `source / header_path / score` 的切片。
- **兜底**：知识库无结果或需最新信息时，Agent 调 `web_search`（DashScope 远程 MCP `bailian_web_search`）。

### 记忆机制

- **短期记忆**：进程内 `InMemoryMemory`，同一会话内保留上下文，新会话自动清空。
- **长期记忆**：`Mem0LongTermMemory`（`agent_control` 模式），Agent 在对话中自主调用 `record_to_memory` / `retrieve_from_memory`，跨会话积累用户画像，向量存 Qdrant（`mem0` 集合，2048 维）。

### 异步文档解析

上传的文件进 MinIO，任务入 RabbitMQ `doc_parse` 队列；`ai-worker` 消费后解析（docx / pdf / 图片 OCR，见 `understanding.py`），`chat` 类型结果写 Redis 供网关轮询，`ingest` 类型额外经 gRPC `IngestText` 写入课程库。

## 存储设计

| 组件 | 存储内容 | 说明 |
| :--- | :--- | :--- |
| MySQL | User / Session / Message / Attachment | 核心业务元数据（GORM） |
| Redis | 限流计数、JWT 黑名单、解析结果缓存 | 高并发读写 |
| RabbitMQ | doc_parse 异步文档解析队列 | 可靠投递 + 削峰 |
| Qdrant | 课程知识库（acp_docs）+ 长期记忆（mem0） | 两类语义检索共用一个实例 |
| MinIO | 用户上传的附件实体 | MySQL 仅存 URL 与元数据 |

## API 一览

| 方法 | 路径 | 鉴权 | 说明 |
| :--- | :--- | :--- | :--- |
| POST | /api/auth/register | 无 | 注册 |
| POST | /api/auth/login | 无 | 登录，返回 JWT |
| GET | /api/auth/me | JWT | 当前用户信息 |
| POST | /api/auth/logout | JWT | 登出（jti 进 Redis 黑名单） |
| POST | /api/assistant | JWT + 限流 | 统一对话入口，SSE 流式 |
| POST | /api/files/upload | JWT + 限流 | 上传附件（task_type=chat/ingest），返回 task_ids |
| GET | /api/files/status | JWT + 限流 | 查询解析任务状态 |
| POST | /api/admin/reindex | JWT + admin | 清空重建课程知识库 |
| POST | /api/admin/kb/add | JWT + admin | 单篇入库 |
| GET | /health、/metrics | 无 | 健康检查 / Prometheus 指标 |

SSE 事件类型：`step`（工具轨迹）/ `delta`（逐段文本）/ `sources`（引用来源，预留）/ `done` / `error`。

## 目录结构

```text
Agent/
├── proto/assistant.proto            # gRPC 契约（Chat / IngestText / Reindex）
├── gateway/                         # Go 接入层
│   ├── cmd/gateway/main.go          # 启动入口（RabbitMQ 重试、管理员种子）
│   ├── internal/{api,auth,config,database,models}
│   └── gen/assistant/v1/            # gRPC 桩（protoc 生成）
├── ai-engine/                       # Python AI 引擎
│   ├── app/
│   │   ├── main.py                  # FastAPI + lifespan 启动 gRPC server
│   │   ├── grpc_server.py           # gRPC 服务实现
│   │   ├── assistant.py             # AgentScope 统一入口 + mem0 记忆
│   │   ├── rag.py                   # LlamaIndex + Qdrant RAG 管线
│   │   ├── understanding.py         # 文档解析（docx/pdf/OCR）
│   │   ├── mcp_search.py            # DashScope 联网搜索
│   │   ├── worker.py                # 异步文档解析 worker
│   │   └── config.py / metrics.py
│   ├── data/docs/                   # 课程知识库文档（挂载，可重灌）
│   └── gen/                         # Python gRPC 桩
├── frontend/                        # Vue 3 + Vite
│   ├── src/{App.vue,api.js,main.js}
│   └── dist/                        # 构建产物（npm run build 生成，不进版本控制）
├── feishu-adapter/                  # 飞书适配器（长连接 + CardKit 流式 + 图片）
│   └── app/{main,bot,card,feishu_api,gateway,config}.py
├── deploy/
│   ├── nginx.dev.conf               # 本地开发（8081 / 8443）
│   ├── nginx.conf                   # 生产（80 / 443 + ACME + 跳转 HTTPS）
│   ├── prometheus.yml
│   ├── certs/                       # TLS 证书（自签名 / Let's Encrypt，不入库）
│   └── certbot/www/                 # ACME webroot（不入库）
├── renew_cert.sh                    # Let's Encrypt 自动续期（配 cron）
├── scripts/                         # 冒烟脚本 + _codegen.ps1（桩代码生成）
├── docker-compose.yml
└── .env.example
```

## 技术栈

- **接入层**：Go（Gin、GORM）、gRPC
- **AI 引擎**：Python（FastAPI）、AgentScope（ReActAgent）、LlamaIndex（RAG）、mem0（长期记忆）
- **前端**：Vue 3 + Vite、marked（Markdown 渲染）+ DOMPurify（清洗）+ highlight.js（代码高亮）
- **飞书**：lark-oapi 长连接 + CardKit v1 流式卡片
- **存储**：MySQL、Redis、RabbitMQ、Qdrant、MinIO
- **模型**：阿里云通义千问（qwen-plus / text-embedding-v4 / gte-rerank / qwen-vl-ocr）
- **工程化**：Docker Compose、Prometheus、Grafana、Let's Encrypt（certbot）

## 已知限制与后续

- **引用来源面板**：`search_course` 已在工具返回的 metadata 里携带 sources，但流式事件尚未把 `sources` 透传到前端，目前引用以 `[编号]` 内嵌正文展示，前端「引用来源」面板暂为空。
- **短期记忆为进程内**：`ai-engine` 当前单实例部署，短期记忆不跨实例共享；水平扩展前需改为 Redis 等共享存储。
- **安全护栏与评测**：原设计中的输入/输出内容审核与 Ragas 评测链路尚未接入当前实现。

## 路线图

- [x] Phase 1：基础架构（Go + Gin + MySQL + JWT + FastAPI）
- [x] Phase 2：纯文本对话链路
- [x] Phase 3：RAG 知识库检索（LlamaIndex + Qdrant）
- [x] Phase 4：Agent 引入与工具调用（AgentScope + 联网兜底）
- [x] Phase 5：长期记忆集成（mem0）
- [x] Phase 6：异步文档解析（RabbitMQ + MinIO + OCR）
- [x] Phase 7：工程化与监控（Docker Compose + Prometheus + Grafana）
- [x] Phase 8：统一入口重构（gRPC 契约 + 统一 /api/assistant）
- [x] Phase 9：飞书渠道（CardKit 流式卡片 + 图片）、生产 HTTPS（Let's Encrypt + 自动续期）、前端 Markdown 渲染与代码高亮
