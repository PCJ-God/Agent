# Agent 智能教学助手 — 当前计划与工作记录

> **定位**：本文件是**当前**的计划与改动记录。早前一次会话的记录已归档到
> `docs/plan-review-archive.md`，其中的问题清单多已处理，**不要作为现状参考**。
>
> **记录范围**：用户体系与公网部署这一轮（认证、用户隔离、资源限制、Qdrant server 模式、
> HTTPS 与反向代理）。行号与默认值以磁盘实际内容为准。
>
> 约定：每条改动给出「原因 + 验证证据」；**没有验证的会明确标注未验证**。

---

## 一、本轮解决的问题

上一轮结束时，这个服务**没有任何身份概念**：谁都能调所有接口，所有用户的会话共用一张表，
长期记忆里的 `user_id` 是硬编码的字面量 `"user"`。换句话说，只要有第二个人用，两个人的
对话和记忆就会混在一起。

本轮把它改成一个可以放到公网的多用户服务，并补上部署路径。

---

## 二、当前状态

### 2.1 隔离模型

两层隔离：**用户** 与 **任务**。

| 层面 | 隔离方式 |
|------|----------|
| 用户 | `users` 表 + uuid token；除 `/health` 外所有接口要求 `Authorization: Bearer <token>` |
| 短期记忆 | 每个 (用户, 任务) 一个 `HierarchicalTeam`，各自一份 `InMemoryMemory` |
| 长期记忆 | Mem0 作用域三元组 `(agent_id="TeachingTeam", user_id=<真实用户>, run_id=<任务>)` |
| 对话历史 | SQLite `data/sessions.db`，表 `sessions`/`messages` 都带 `user_id` |
| 并发 | 锁按 (用户, 任务) 分 —— 不同任务可并行，同一任务内串行 |

### 2.2 部署形态与配置项

两种形态，均已实现：

- **挂反向代理（推荐）**：应用只监听 `127.0.0.1:8000`，TLS 由代理终止
- **直连 HTTPS**：配 `SSL_CERTFILE` / `SSL_KEYFILE`，由 uvicorn 终止 TLS

| 配置项 | 默认 | 作用 |
|--------|------|------|
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 监听地址 |
| `SSL_CERTFILE` / `SSL_KEYFILE` | 空 | 直连 HTTPS；挂代理则留空 |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | 信任哪些来源的 `X-Forwarded-*`，**不要填 `*`** |
| `QDRANT_URL` / `QDRANT_API_KEY` | 空 | 填了走 Qdrant server，否则退回本地文件模式 |
| `MAX_SESSIONS_PER_USER` | 50 | 每人任务数上限 |
| `MAX_TEAMS` | 20 | 进程内保留的团队实例上限，超出按 LRU 淘汰空闲的 |
| `RATE_LIMIT_PER_MINUTE` | 20 | 每人每分钟对话请求上限 |
| `LTM_SCOPE` | `session` | `session` 每任务独立 / `global` 跨任务累积 |

---

## 三、改动清单

### 3.1 新增认证层

新增 `src/access/auth.py`：一个 FastAPI 依赖 `current_user`，把
`Authorization: Bearer <token>` 换成用户身份。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 发一个 uuid4 token，返回 `{user_id, token, name, created_at}` |
| `GET` | `/api/auth/me` | 校验 token，返回当前用户 |

除 `/health` 外所有接口挂 `Depends(current_user)`。`session_store.revoke_token(token)` 可吊销。

**设计要点**：`user_id` 与 `token` 是**两个不同的 uuid**。因为长期记忆会把 `user_id` 写进
向量库的 payload，而 token 是凭证 —— 凭证不该出现在数据库的元数据里。

**已知取舍**：token 是「用户名 + 密码」合一，只能靠 HTTPS 保护。要接真正的登录体系，
只需替换 `current_user`，下游一行都不用改。

### 3.2 长期记忆按用户隔离（本轮最关键的一处）

`src/orchestration/hierarchical.py`：

```diff
-        user_name="user",          # 字面量 → 所有用户共用同一个记忆域
+        user_name=user_id,         # 来自认证层
```

这一行是上一轮那个「两个用户会不会读到彼此记忆」问题的真正开关。改后作用域实测为
`user_id='alice' / 'bob'`，即使 `run_id`（任务）相同也互不可见。

### 3.3 会话归属用户 + 数据迁移

`src/storage/memory/session_store.py`：

- 新增 `users` 表（`user_id` / `token` / `name` / `created_at`）
- `sessions` 主键由 `id` 改为复合主键 `(user_id, session_id)`
- `messages` 增加 `user_id` 列，索引按新主键重建
- 所有读写函数签名加上 `user_id`
- 服务端团队缓存键由 `session_id` 改为 `(user_id, session_id)`

**自动迁移（v1 → v2）**：检测到旧表结构时，把旧 `sessions`/`messages` 整体挂到一个名为
`legacy` 的用户下，再删旧表。**旧数据不丢**，但归属到 `legacy`（旧数据本来就没有用户维度，
只能这么兜）。

### 3.4 资源隔离

- `MAX_SESSIONS_PER_USER`：建任务时检查，超出返回 429
- `MAX_TEAMS`：进程内团队缓存上限，超出按 LRU 淘汰**空闲**团队（正在对话的不踢；
  历史仍在 SQLite，下次访问重建）
- `RATE_LIMIT_PER_MINUTE`：按用户计数的滑动窗口，超出返回 429

**顺带修掉一个并发缺陷**：原先团队装配（要 10–20 秒）是在注册表锁**内**做的，
等于一个用户的首次请求会把其他所有用户堵住。现在装配移到锁外，锁内只做缓存读写。

**去掉启动预装配**：多用户下不存在「默认会话」，且每个团队自带 MCP 客户端，预热一个并不能
加速别人的首次请求。副作用是 `/health` 的 `mcp` 在首个对话前显示 `initializing`（如实反映，
不是故障）。

### 3.5 Qdrant server 模式

`src/config.py` + `src/storage/memory/long_term.py`：设了 `QDRANT_URL` 走 server 模式，
否则退回本地文件模式并**在启动时告警**：

```text
长期记忆: 本地文件模式 (./data/memory/qdrant) —— 单进程独占，不要用于公网部署；线上请设 QDRANT_URL
```

这一步不是隔离的修复，是**部署前提**：本地文件版单进程独占，多 worker 根本起不来。

### 3.6 HTTPS 与反向代理

| 文件 | 内容 |
|------|------|
| `deploy/nginx.conf` | Nginx 反代 + TLS，含 SSE 关键指令与网关级限速 |
| `deploy/Caddyfile` | Caddy 版（自动申请续期证书） |
| `scripts/gen_self_signed_cert.py` | 生成自签证书（含 SAN），仅本地验证用 |
| `docs/DEPLOY.md` | 两种形态的完整步骤、上线检查清单、排错表 |

`src/access/server.py` 的 `run()` 支持两种形态，并开启 `proxy_headers` / `forwarded_allow_ips`
（否则日志里客户端 IP 全是代理地址）。

**SSE 的四条关键指令**（`docs/DEPLOY.md` 有解释）：`proxy_buffering off`、`gzip off`、
`proxy_http_version 1.1` + `Connection ''`、`proxy_read_timeout 600s`。

### 3.7 前端

`frontend/index.html`：首次打开自动注册并把 token 存 `localStorage`；新增 `api()` 统一入口
自动带凭证，遇 401 自动重注册并重试一次；页脚显示用户名与当前任务；任务列表改读 `session_id`。

### 3.8 文档与工程杂项

- `README.md`：新增「用户、会话（任务）与记忆」章节（认证、任务接口、资源隔离表）
- `.env.example`：新增监听/HTTPS/资源隔离各项
- `.gitignore`：挡掉 `data/certs/`、`*.pem`、`*.key` —— **私钥不能进仓库**

### 3.9 验证途中修掉的 bug

`GET /api/sessions` 抛 `ResponseValidationError`：3.3 把列名 `sessions.id` 改成 `session_id`，
但 pydantic 模型 `SessionInfo` 还叫 `id`。**这是端到端验证抓出来的**，不是读代码发现的。
修复：`SessionInfo.session_id` + 前端 `s.id` → `s.session_id`。

---

## 四、验证记录

### 4.1 存储层（跨用户隔离）

两个用户使用**同一个** `session_id`：

```text
[alice] total=2 -> ['alice的提问', 'alice的回答']
[bob]   total=2 -> ['bob的提问', 'bob的回答']
```

其余：迁移后 `legacy` 用户下旧数据仍在；第 21 次/分钟被拒 `429`，另一用户不受影响；
吊销后 token 失效。

### 4.2 长期记忆作用域

同一任务 ID、两个用户：

```text
[alice] user_id='alice' run_id='shared-task' agent_id='TeachingTeam'
[bob]   user_id='bob'   run_id='shared-task' agent_id='TeachingTeam'
```

### 4.3 API 端到端

```text
未认证 GET /api/sessions   -> 401
POST /api/auth/register ×2 -> 两个不同 user_id
两个用户同 session_id 各问一句 -> 各 200
alice 只看到 alice 的 2 条；bob 只看到 bob 的 2 条
GET /api/sessions 字段名: ['created_at','messages','session_id','title','updated_at']
第 51 个任务 -> 429 任务数已达上限 50
DELETE 任务 -> 200，列表随之减少
```

### 4.4 HTTPS 直连

```text
https://127.0.0.1:8443/health -> 200
明文 HTTP 打 TLS 端口         -> 连接被拒
未认证 -> 401；带 token -> 200
SSE: 38 帧，首帧 +2.22s，末帧 +2.64s（两次不同投递，无整体缓冲）
```

### 4.5 真实 nginx 反向代理

用 nginx 1.30.5（Windows 版）实跑，`deploy/nginx.conf` 的指令集搬到本地端口：

```text
nginx -t                       -> syntax is ok / test is successful
http://localhost:8080/health   -> 301，Location: https://localhost:8443/health
https://localhost:8443/health  -> 200（TLS 由 nginx 终止，回源 127.0.0.1:8000）
未认证经代理 /api/sessions      -> 401（Authorization 透传正常）
前端 / 与 /static/index.html    -> 200
```

### 4.6 SSE 缓冲 A/B（同一请求，只改代理配置）

```text
proxy_buffering off（交付配置）: 首帧 +9.34s / 总 27.06s → 35%   1956 帧
proxy_buffering on （nginx 默认）: 首帧 +15.31s / 总 24.39s → 63%   1020 帧
```

结论：缓冲让首字节晚约 6 秒，输出块变粗。对照组没到 100% 是因为 nginx 按缓冲块刷，
这次回答小到只填满一块。回答越长，差异越明显。

### 4.7 验证边界（未覆盖，如实说明）

- **Caddy 那版没有实测**（机器上没装 Caddy）。`flush_interval -1` 是官方做法，但我没跑过。
- **真实 Let's Encrypt 链路没走**，用的是自签证书且客户端关了校验。
- **代理实测跑的是本地改写版配置**（端口 8080/8443、证书路径不同），验证的是指令集与整体
  结构，不是 `deploy/nginx.conf` 原文逐字加载。
- **LRU 淘汰只做了逻辑层面验证**，没在并发下压测。
- **限流与 `MAX_TEAMS` 是进程内的**，多 worker 下每个 worker 各算一份 —— 见第七节。

---

## 五、实测数据（服务器选型依据）

```text
解释器刚起来:         13.7 MB
import 全部依赖后:   146.6 MB   ← 空载基线（大头在这里）
1 个团队:            155.7 MB   (+9.1)
2 个团队:            156.0 MB   (+9.4)
3 个团队:            156.1 MB   (+9.5)
4 个团队:            156.2 MB   (+9.6)   ← 4 个团队合计才 +9.6 MB
正在运行的真实实例:  173.5 MB   （2 个团队 + 真实对话历史）
site-packages 体积:  1870 MB
data/ 体积:          0.1 MB
```

**两个结论：**

1. **内存几乎不随团队数增长** —— MCP 客户端与 Qdrant 客户端在进程内是共享的，每个团队只
   多出几个 Agent 对象和一段对话历史（约 0.1 MB）。
2. **磁盘要给够** —— 光依赖就 1.87 GB。

**选型建议：2 核 2G、40G 磁盘。** 4G 的唯一理由是同机再跑 Qdrant server 与 Docker。
CPU 稳态几乎不吃（都在等 DashScope），吃 CPU 的是启动与团队装配这类短时突发。
真正的约束是 DashScope 配额/费用、磁盘、以及单任务串行 —— **都不是机器规格**。

---

## 六、上线待办

### 6.1 硬前提

- [ ] **`QDRANT_URL`（仅多 worker 需要，不是上线前提）**：不配就只能是单进程；而单进程正是
      这个应用的推荐形态（见第七节第 1 条），所以初次上线**可以先不配**，本地文件版 Qdrant 够用。
- [ ] **`agentscope>=0.1.0` 下限过松**（`requirements.txt:4`）：代码用的是 AgentScope 1.x API，
      全新服务器上 `pip install` 可能装出 0.x 直接跑不起来。建议收紧到 `>=1.0.0`。
- [ ] **`cryptography` 不在依赖清单里**：`scripts/gen_self_signed_cert.py` 依赖它，目前只是
      恰好被其他包间接装上。要么加进 `requirements.txt`，要么接受该脚本只在已有环境可用。

### 6.2 上线必须补

- [ ] **systemd unit**（Linux）：`Restart=always`、开机自启、日志进 journald、专用低权限用户。
      **陷阱**：`src/config.py:9` 是 `load_dotenv()`（无参数，按当前工作目录找 `.env`），
      所以 `WorkingDirectory=` 必须写对，否则 `.env` 找不到、`check_api_key()` 直接启动失败。
- [ ] **备份 `data/`**：里面是所有人的会话与长期记忆，丢了不可逆。
- [ ] **HTTPS 生效**：按 `docs/DEPLOY.md` 的检查清单逐条过，重点是 `FORWARDED_ALLOW_IPS`
      不要填 `*`。

### 6.3 建议

- [ ] 部署地区决策（大陆需 ICP 备案、延迟好；香港免备案、延迟与带宽差）
- [ ] Caddy 版配置实测（若决定用 Caddy）
- [ ] `invoke_reviewer` 路径的运行时验证（承自归档文档 4.6，仍未覆盖）

---

## 七、已知限制

1. **必须单 worker。** 限流计数、任务锁、团队缓存都是进程内的（`src/access/server.py` 的
   `_rate` / `_locks` / `_teams`）。多 worker 会导致：限流额度变成 N 倍、**同一个任务可能在两个
   worker 里同时跑**（Leader 的记忆不是并发安全的）、每 worker 各建一份团队。
2. **多 worker 对当前瓶颈帮助很小。** 应用是 I/O 密集型的，并发靠 `asyncio`，单 worker 就能
   同时服务很多用户。真要扩，更可能是多机 + 反向代理，而那种情况下第 1 条同样存在。
3. **限流是两层**：应用层「每用户每分钟 N 次」+ 网关层「每 IP 每秒 N 次」（`deploy/nginx.conf`）。
   两层互补，不是替代。
4. **无需配 CORS**：前端与 API 同源。除非将来把前端分域部署。
5. **token 存 `localStorage`**：因此 HTTPS 不是可选项 —— 没有 HTTPS 就等于没有认证。

---

## 八、本轮纠正过的错误判断

记录在案，避免重复：

1. **「内存是瓶颈，靠 `MAX_TEAMS` 兜住」** —— 被实测否掉。20 个团队约 2 MB，团队几乎不占内存。
2. **把「先做哪个」写成「只能选一个」（两次）** —— 第一次把「HTTPS 与 Redis 限流」并列成
   或者关系；第二次把「Caddy 实测」与「systemd」并列。前者其实是顺序问题，后者里 Caddy 实测
   价值接近零（验的是别人的软件，且只在选 Caddy 时才有意义）。**该给判断的时候不要给菜单。**
3. **测量脚本把 0.0 当成数据打印** —— `GetProcessMemoryInfo` 调用失败但没检查返回值，
   于是打印出一排 `0.0 MB`。修法是设对 `restype/argtypes` 并强制校验返回值。

---

## 九、遗留项（承自 `docs/plan-review-archive.md`，多数未复核）

以下条目来自归档文档第五节，**本轮没有触碰，状态未复核**：

| 原编号 | 问题 | 备注 |
|--------|------|------|
| 5.5 | `short_term.py` 的 `ContextTruncation` 分支用 `OpenAITokenCounter`，会触发 tiktoken 词表下载而**永久卡死** | 该函数目前是死代码，但改动成本极低（换 `CharTokenCounter`） |
| 5.6 | `long_term.py` 的 docstring 仍写着 `both`，签名已不含 | 文档与代码不一致 |
| 5.7 | `mode="both"` 时不会追加记忆工具提示 | 将来允许 `both` 时会踩 |
| 5.8 | `cli.py` 的几个未使用导入、`--interactive` 参数解析后未使用等 | 参见归档文档 |
