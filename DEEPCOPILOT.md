# Deep Copilot 项目备忘（ACP Copilot）

本文件记录该仓库对 AI 编码助手有用的项目事实、约定与踩坑点，供后续会话快速对齐。

## 项目速览

- 类型：阿里云 ACP 学习助手，Go（网关）+ Python（AI 引擎）混合架构，Docker Compose 编排（11 个服务）。
- 唯一对外入口：nginx `:8081`；调试直连网关 `:8080`；AI 引擎 `:8000`（HTTP）/ `:50051`（gRPC）。
- 应用默认管理员：`admin / admin123456`（网关首次启动自动种子创建）。

## 常用命令

```bash
# 网关（Go）
cd gateway && go build ./... && go vet ./...

# AI 引擎（Python 语法检查）
python -m py_compile ai-engine/app/*.py

# 全栈构建启动
docker compose up -d --build

# 重建单个自建服务（必须 --force-recreate，见下方坑 1）
docker compose build ai-engine
docker compose up -d --force-recreate --no-deps ai-engine ai-worker
```

## 关键坑位（务必记住）

1. **`docker compose up -d` 不会在镜像 tag 不变时重建容器**：重新 build 后必须加 `--force-recreate --no-deps <service>`，否则运行中的容器仍是旧镜像。
2. **protobuf gencode 与运行时版本必须匹配**：Python 桩由 `scripts/_codegen.ps1` 用 `grpc_tools.protoc` 生成，gencode 版本 = grpcio-tools 自带 protobuf 版本。requirements 已锁 `grpcio>=1.81.1`、`protobuf>=6.33.5`（对应 gencode 6.33.x）。改 proto 后重跑 `_codegen.ps1`（脚本已内置把 `import assistant_pb2` 修正为 `from gen import assistant_pb2`）。
3. **Docker Desktop 的 `localhost` 会先解析 IPv6 `::1`**，端口转发可能未就绪；命令行验证统一用 `127.0.0.1`（浏览器自动回退不受影响）。
4. **AgentScope 1.0.21 三个易错点**（`ai-engine/app/assistant.py`）：
   - `Toolkit.register_tool_function(json_schema=...)` 必须是 OpenAI function 格式 `{"type":"function","function":{...}}`，裸 `{"type":"object",...}` 会报 `Invalid JSON schema`。
   - 消息队列项是三元组 `(msg, last, speech)`，不是 Msg 对象，需解包。
   - 消息 `content` 里的块是 TypedDict（dict），用 `b["type"]` / `b.get(...)` 访问，不要用 `getattr`。
5. **Qdrant 点 ID 只接受 uint 或 UUID**：给 `TextNode` 设 `id_` 时用 `str(uuid4())`，不能用文件名/序号字符串。
6. **网关冷启动 RabbitMQ 端口可能晚于健康检查就绪**：`gateway/cmd/gateway/main.go` 已加 `dialRabbit` 重试，不要移除。

## 冒烟验证（最小链路）

```bash
# 1) 管理员登录拿 token
curl -s -X POST http://127.0.0.1:8080/api/auth/login -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123456"}'

# 2) 重灌课程库（分块 + 向量化 ai-engine/data/docs，约几十秒）
curl -s -X POST http://127.0.0.1:8080/api/admin/reindex -H "Authorization: Bearer $TOKEN" -d '{}'

# 3) 流式对话（应依次出现 step → delta → done）
curl -N -X POST http://127.0.0.1:8081/api/assistant -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"什么是RAG？","session_id":"s1","task_ids":[]}'
```

## 关键文件地图

| 关注点 | 文件 |
| :--- | :--- |
| gRPC 契约 | `proto/assistant.proto` |
| 网关路由/中间件 | `gateway/internal/api/*.go` |
| 网关启动（RabbitMQ 重试、管理员种子） | `gateway/cmd/gateway/main.go` |
| 统一 Agent 入口 | `ai-engine/app/assistant.py` |
| RAG 管线 | `ai-engine/app/rag.py` |
| 文档解析 | `ai-engine/app/understanding.py` |
| 联网搜索 | `ai-engine/app/mcp_search.py` |
| 异步 worker | `ai-engine/app/worker.py` |
| 前端（Vue） | `frontend/src/App.vue`、`frontend/src/api.js` |
| nginx 反代 | `deploy/nginx.dev.conf` |
