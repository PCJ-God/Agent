# Agent 智能教学助手 — 当前计划与工作记录

> **定位**：本文件是**当前**的计划与改动记录。早前一次会话的记录已归档到
> `docs/plan-review-archive.md`，其中的问题清单多已处理，**不要作为现状参考**。
>
> **记录范围**：用户体系与公网部署这一轮（认证、用户隔离、资源限制、Qdrant server 模式、
> HTTPS 与反向代理），以及随后的**线上落地与域名接入**（腾讯云实例、真实 Let's Encrypt
> 证书、前端致命 bug 修复）。行号与默认值以磁盘实际内容为准。
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

### 2.3 线上部署实况（本轮新增，均为实测）

**服务器**：腾讯云 CVM，Ubuntu 26.04 LTS，内核 7.0.0-30-generic，**2 核 / 1962 MB / 39 GB**
（余 31 GB）。Python 3.14.4。与第五节「2 核 2G、40G 磁盘」的选型建议吻合。

**访问入口**：

| 入口 | 证书 | 说明 |
|------|------|------|
| `https://lovekiki.site` | Let's Encrypt，90 天（标准档案） | 正式入口；DNS A 记录指向本机 |
| `https://www.lovekiki.site` | 同一张证书（SAN 含两个名字） | |
| `https://139.155.146.41` | Let's Encrypt，6 天（`shortlived` 档案） | 备用；域名若被拦仍有退路 |

所有入口的 HTTP 一律 301 到 `https://$host`。

**IP 证书为什么只有 6 天**：Let's Encrypt 的 IP 证书走 `shortlived` 档案，有效期 6 天。
所以**续期必须可靠** —— 已装 cron，并用 `certbot renew --dry-run` 验证通过。
（6 天证书一旦续期失灵，HTTPS 六天后自己就死了。）域名证书是常规 90 天。

**certbot 用 pip 装，不用 snap**：snapcraft 在大陆的访问和 GitHub 一样不可靠，
改用 `python3 -m venv /opt/certbot` + 腾讯云 pip 镜像。

**nginx 结构**：域名与纯 IP 各占一个 443 server 块（原因见 3.12），
两块共用的部分抽到 `/etc/nginx/agent-locations.conf`。

---

## 三、改动清单

### 3.1 新增认证层

新增 `src/access/auth.py`：一个 FastAPI 依赖 `current_user`，把
`Authorization: Bearer <token>` 换成用户身份。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 不带凭据 → 匿名账号（打开即用）；带了 → 具名账号 |
| `POST` | `/api/auth/login` | 用户名 + 密码换一个新 token（见 3.13） |
| `POST` | `/api/auth/bind` | 给当前匿名账号补上用户名密码（见 3.13） |
| `POST` | `/api/auth/logout` | 吊销当前 token |
| `GET` | `/api/auth/me` | 校验 token，返回当前用户 |

除 `/health` 外所有接口挂 `Depends(current_user)`。`session_store.revoke_token(token)` 可吊销。

**设计要点**：`user_id` 与 `token` 是**两个不同的 uuid**。因为长期记忆会把 `user_id` 写进
向量库的 payload，而 token 是凭证 —— 凭证不该出现在数据库的元数据里。

**演进**：3.13 在这个基础上加了账号密码登录。`current_user` 的位置没变，下游
（记忆作用域、会话归属、配额）一行都没改 —— 当初留的这个口子是有效的。
**仍然保留的取舍**：token 依旧是「一票通行」的凭证，只能靠 HTTPS 保护，
拿到 token 就等于拿到账号（密码是另一条独立的路）。

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

### 3.10 前端发送按钮完全失效（顶层 TDZ 异常）

`frontend/index.html` 里 `renderFooter()` 在 `mcpFooter` 的 `const` 声明**之前**被调用，
而 `mcpFooter` 处于暂时性死区，该调用直接抛：

```text
ReferenceError: Cannot access 'mcpFooter' before initialization
```

它位于内联脚本的**顶层**，异常中断整个脚本 —— 于是后面的
`sendBtn.addEventListener('click', sendMessage)` 与回车键监听**从未执行**。
症状：输入框能打字（那是纯 HTML，不需要 JS），但点「发送」和按回车都毫无反应。

修复：把 `renderFooter()` 移到元素 `const` 声明之后。

**这个 bug 从部署那一刻就存在，与网络、与 CDN 都无关，任何环境下都一样坏。**

### 3.11 systemd unit 的 `StartLimit*` 写错了分段

`deploy/agent.service` 里 `StartLimitBurst` / `StartLimitIntervalSec` 原本写在 `[Service]`，
systemd 在 journal 里报：

```text
Unknown key 'StartLimitIntervalSec' in section [Service], ignoring
```

这两个键属于 `[Unit]`。被静默忽略意味着「连续快速失败就放弃」这层保护**从未生效**，
而读文件的人会以为它生效了。修复：移到 `[Unit]`。
**是在 journal 里看到告警才发现的，不是读代码发现的。**

### 3.12 Nginx 支持域名（域名与纯 IP 各占独立 443 server 块）

拿到域名后签了域名证书，并调整 nginx 结构：

| 文件 | 内容 |
|------|------|
| `deploy/nginx.conf` | 两个 443 server 块（域名块 / 纯 IP 块），证书随块走 |
| `deploy/agent-locations.conf` | 新增：两块共用的 TLS 参数 + 超时 + location 转发 |

**为什么必须拆成两个块**：nginx 按 `server_name`（SNI）选 server 块，证书是随块走的。
在**同一个**块里写多个 `ssl_certificate` 并不能实现「按 SNI 选证书」—— 那个写法是给
同一域名同时配 RSA 和 ECDSA 用的。实测把两张证书塞进一个块，域名访问也会拿到 IP 证书，
浏览器报名称不匹配，**比不改还糟**。

片段文件放 `/etc/nginx/agent-locations.conf`，**不能放 `conf.d/`**：
那里被 `include /etc/nginx/conf.d/*.conf` 做 http 级包含，而 `location` 块
只能出现在 `server` 块里，放进去 nginx 直接起不来。

### 3.13 账号密码登录（可迁移的凭证）

**起因**：原机制是「匿名自动注册 + 无密码 token」，token 存在浏览器 localStorage。
换设备 / 换浏览器 / 清缓存之后，服务端数据明明都按 `user_id` 存着，但**没有任何办法
再证明自己是那个 user_id** —— 历史等于拿不回来。要「登录后看到自己的历史」，
缺的正是**可迁移的凭证**。

| 文件 | 内容 |
|------|------|
| `src/access/passwords.py` | 新增：scrypt 哈希 + 用户名/密码格式校验 |
| `src/storage/memory/session_store.py` | `users` 加 `username`/`password_hash`；新增 `tokens` 表与 `_migrate_v2` |
| `src/access/server.py` | 新增 `login` / `bind` / `logout`；`register` 支持带凭据 |
| `src/access/auth.py` | 新增 `bearer_token` 依赖（登出要拿 token 原文） |
| `frontend/index.html` | 顶栏「账号」按钮 + 面板（绑定 / 登录 / 退出） |

**为什么用标准库 scrypt**：依赖钉死在 `constraints.txt` 的实测组合上（110 个包），
每加一个包都要在 Python 3.14 上重新验证一遍，而 PyPI 只走国内镜像。`hashlib.scrypt`
是内存硬的 KDF，强度够用且零新依赖。存储串自描述
（`scrypt$n=..,r=..,p=..$salt$hash`），将来换 argon2 只需按前缀分派。

**为什么把凭据「绑」到现有账号，而不是新建账号再搬历史**：`user_id` 是数据归属的唯一
依据（会话、消息、长期记忆都按它隔离）。搬历史要跨三套存储做复制，任何一步失败都会留下
半迁移状态；把凭据绑到现有 `user_id` 上，历史天然就在原地。所以网页端「设置用户名密码」
走的是 `bind`，不是「注册新账号」。

**`users.token` 这列怎么处理**：它是历史列（`NOT NULL UNIQUE`），不能直接删。做法是新老
并存 —— 存量值一次性搬进 `tokens` 表（老客户端不掉线），之后认证只看 `tokens`；
`revoke_token` 会把这一列的值改成哨兵值，避免留下「看起来还能用」的凭证。

**踩到的坑（副本测试抓出来的）**：搬存量 token 的语句如果每次 `init_db()` 都跑，那么
`users.token` 里**之后才出现**的值（也就是登出写的哨兵值）会在下次重启时被当成有效凭证
重新插进 `tokens` 表 —— 一个已吊销的凭证「复活」了。修法是**只在 `tokens` 为空时搬**：
这是一次性搬迁，不是每次启动的例行动作。

**登录失败节流**：按用户名记失败次数（5 分钟窗口 / 8 次），超限 429。**取舍**：按用户名
计数意味着攻击者能用错误密码把某个已知账号短暂锁住；更稳妥要「账号 + 来源 IP」双维度，
那需要 nginx 传真实 IP。

**前端顺带避开的一处同类隐患**：`ACCOUNT` 是 `let`，且被 `renderFooter()` 读。
它必须声明在 `renderFooter()` **首次调用之前**，否则就是 3.10 那个 TDZ 崩溃的翻版。
已在声明处写明原因（4.10 的三层检查会拦住这类回归）。

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
- **账号面板没在真实浏览器里点过**（见 3.13）。Node + DOM 桩覆盖了逻辑分支与 id 引用，
  但样式、布局、真实事件绑定仍需人点一遍 —— 这是本轮最该补的一项。
- **登录失败节流按用户名计数**，所以存在「用错误密码把别人账号锁住」的可能（5 分钟）。
- **密码只校验长度**（8-128），没有字典/复杂度检查，也没有「改密码 / 忘记密码」流程 ——
  设错了当前只能换个用户名。
- **scrypt 的代价参数是本地量的**（单次约 39ms、16MB），没测并发登录下的表现。

### 4.8 线上真机验收（真实 Let's Encrypt + 真实公网）

在服务器上实跑，**客户端不关证书校验**（这是与 4.4/4.5 的关键区别：
那两节用的是自签证书且关了校验，验的是配置结构，不是真实证书链）：

```text
https://lovekiki.site/             -> 200  text/html; charset=utf-8
https://www.lovekiki.site/         -> 200
https://lovekiki.site/api/sessions -> 401
http://lovekiki.site/              -> 301  Location: https://lovekiki.site/
https://139.155.146.41/health      -> 200

按 SNI 取到的证书：
  SNI=lovekiki.site      -> CN=lovekiki.site
                            SAN: DNS:lovekiki.site, DNS:www.lovekiki.site
  SNI=139.155.146.41     -> SAN: IP Address:139.155.146.41
```

### 4.9 SSE 经真实 nginx 的流式验收

`POST /api/chat/stream` 经 nginx，逐事件打到达时间戳：

```text
[+  1.12s] data: {"type":"chunk","name":"Project Leader","text":"用户"}
[+  2.13s] ...
[+  9.94s] ...
[+ 44.36s] data: {"type":"done","response":"..."}
共 322 行, 总耗时 44.37s
```

事件从 1.12 秒一路铺到 44 秒 —— **时间戳递增本身就证明没有被缓冲**
（若被缓冲，全部会挤在最后一刻）。`proxy_buffering off` 在真实链路上生效。

### 4.10 前端脚本可执行性检查（可复现的回归手段）

用 Node + 极简 DOM 桩执行 `frontend/index.html` 的内联脚本
（`node scripts/check_frontend.js`，从哪个目录跑都可以），三层检查，从弱到强：

```text
1) 顶层执行不抛异常
   修复前: ReferenceError: Cannot access 'mcpFooter' before initialization
   修复后: 顶层执行完成，没有抛异常

2) getElementById 引用的 id 在 HTML 里都存在
   （桩是"什么都能设"的假元素，所以 id 打错时第 1 层照样通过，浏览器里却会崩）

3) 交互路径真跑一遍（绑定 / 登录 / 退出）
   只看顶层不抛，说明不了这些分支是对的
```

**为什么需要这个手段**：HTTP 层返回 200 并不等于页面能用。3.10 那个 bug 在
「`/health` 200、`/` 返回 24KB HTML、SSE 流式正常」的情况下，页面依然完全不可用。
只验证 HTTP 层会漏掉这一类问题。

### 4.11 账号密码：副本 → 线上迁移 → 真机端到端

**第一步，在数据库副本上验迁移**（服务不动，把模块级 `SESSIONS_DB` 指向副本）：

```text
结果: 全部通过   (44 项)
  迁移不丢人              33 -> 33
  老 token 仍能查到用户     ✓
  tokens 无孤儿             ✓
  重复 init_db 不改动任何一行 ✓ ← 正是这一项抓出了"哨兵值复活"的 bug（见 3.13）
```

**第二步，线上迁移**（备份 → 装代码 → 显式触发迁移）：

```text
迁移前备份 (users, sessions, messages): (34, 4, 14)
迁移后线上 (users, sessions, messages): (34, 4, 14)    ← 不丢任何一行
users 列 : [... 'username', 'password_hash']
tokens=34   孤儿token=0   integrity_check: ok
重复 init_db: 行数一动不动
```

**一个容易误判的点**：`init_db()` 是**惰性**的，重启服务并不会触发迁移 ——
要等第一次真正访问存储层。所以「重启完就去看 schema」会把还没迁移误判成迁移失败
（这次就先误判了一次），得显式调一次 `init_db()` 或用一次真实请求触发。

**第三步，端到端**（`https://lovekiki.site`，TLS + nginx + 应用，不绕任何一层，29 项全过）：

```text
存量老 token                -> 200        迁移没把现有用户踢下线
匿名注册                    -> 200        token 43 字符（旧的 uuid4 是 32）
匿名建任务 → bind 凭据       -> 200        user_id 不变（历史在原地）
换设备用密码登录             -> 200        新 token、同一 user_id
  ★ 新设备看到那份历史        -> 200        ← 整个改动的目的
密码错 / 用户名不存在         -> 401
用户名大写                   -> 200        不区分大小写
密码 4 位 / 用户名重复        -> 400 / 409
登出                        -> 200        该 token 变 401，同账号另一 token 仍 200
```

**第四步，前端**（`node scripts/check_frontend.js`）：

```text
1) 顶层执行没有抛异常                              ✓
2) 12 个 getElementById 的 id 在 HTML 里都存在       ✓
3) 交互路径 7 项全 PASS：
   openAccount / renderAccount(anon|login|named) /
   submitBind / submitLogin（含换账号）/ submitLogout / closeAccount
```

第 3 层顺带验了「换账号不会把上一个账号的任务 ID 带过去」：调用序列里绑定时是
`web-mf8dtqpq`，登录后变成 `web-g1tv8x2q`。

**线上前端一致性**：本地 / 服务器上的文件 / HTTPS 实际返回，三份 md5 相同
（`be543ab4d9e0b06768c170057250026c`）—— 浏览器收到的就是本地测过的那一份。

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

## 六、上线待办与完成情况

### 6.1 硬前提

- [x] **`QDRANT_URL`**：本次上线**未配**，走本地文件模式。单进程正是这个应用的推荐形态
      （见第七节第 1 条），所以初次上线可以先不配，本地文件版 Qdrant 够用。
- [x] **`agentscope` 版本下限过松**：`requirements.txt` 的松下限（`>=0.1.0`）**没改**，
      改为用 `constraints.txt` 钉死实测版本（`agentscope==1.0.18` 等），并在
      `requirements.txt` 顶部写明必须配合 `-c constraints.txt` 安装。
- [ ] **`cryptography` 不在依赖清单里**：`scripts/gen_self_signed_cert.py` 依赖它，目前只是
      恰好被其他包间接装上。要么加进 `requirements.txt`，要么接受该脚本只在已有环境可用。
      **本轮复核**：服务器上装到的是 50.0.1，但 `requirements.txt` 与 `constraints.txt`
      里都没有它 —— 仍在。线上用真实证书，该脚本用不到，影响可忽略，但**未修**。

### 6.2 上线必须补

- [x] **systemd unit 已上线**：`Restart=always`、`enabled` + `active`、日志进 journald、
      专用低权限用户 `agent`。
      **陷阱**：`src/config.py:9` 是 `load_dotenv()`（无参数，按当前工作目录找 `.env`），
      所以 `WorkingDirectory=` 必须写对，否则 `.env` 找不到、`check_api_key()` 直接启动失败。
      （这个陷阱在线上被独立验证过一次：手动前台启动时若不在 `/opt/agent` 下跑，启动即失败。）
      **期间修掉一个 bug**：`StartLimit*` 原本写在 `[Service]` 段被 systemd 静默忽略，见 3.11。
- [ ] **备份 `data/` 未做**：里面是所有人的会话（`data/sessions.db`）与长期记忆
      （`data/memory/`），丢了不可逆。**这仍是当前最该补的一条。**
      **本轮进展**：数据库改动时留下了迁移前快照 `data/sessions.db.pre-v2.bak`（含
      `integrity_check: ok`），但那是手工的一次性快照，**不是备份机制** —— 该项仍未完成。
- [x] **HTTPS 已生效**：真实 Let's Encrypt 证书，域名 + 纯 IP 两个入口，续期 cron 已装并用
      `--dry-run` 验证通过。`FORWARDED_ALLOW_IPS` 保持 `127.0.0.1`。验证见 4.8 / 4.9。

### 6.3 建议

- [x] **部署地区决策**：大陆腾讯云（成都），域名 `lovekiki.site` 已解析到本机。
      **备案待确认**：域名解析到大陆服务器，未备案可能被按域名拦截；
      因此保留了纯 IP 入口作为退路（见第七节第 6 条）。
- [ ] Caddy 版配置实测（若决定用 Caddy）
- [ ] `invoke_reviewer` 路径的运行时验证（承自归档文档 4.6，仍未覆盖）
- [ ] **MCP 从未被真实触发**：`/health` 的 `mcp` 一直是 `initializing`，
      两次真实对话都没有走联网搜索。**这条路完全没有验证。**
- [ ] **前端依赖 jsdelivr CDN，大陆实测不通**：`frontend/index.html` 引用 5 个
      `cdn.jsdelivr.net` 资源（katex / marked / DOMPurify）。大陆实测**5 个全部返回 `000`**
      （0.22 秒被重置，curl 退出码 35）。代码有优雅降级，**不会崩**，
      但消息会退化为**纯文本**：公式不排版、代码块不高亮。
      修法是自托管这 5 个文件（注意：从大陆也下不了 jsdelivr，需走 npm 镜像）。

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
6. **域名可用性不由本机决定。** 域名解析到大陆服务器，未备案可能被按域名拦截
   （表现为域名突然不通，而纯 IP 仍正常）。故保留纯 IP 入口（独立 server 块 + IP 证书）
   作为退路。但 IP 证书走 `shortlived` 档案**只有 6 天**，续期失灵 = HTTPS 六天后失效，
   所以两个入口都依赖同一条续期 cron。
7. **账号密码没有「改密码 / 忘记密码」**：`attach_credentials` 只允许匿名账号绑一次，
   具名账号不能被覆盖，所以密码设错了当前只能换个用户名重新绑定（见 4.7）。
   token 依旧是 `localStorage` 里的一票通行凭证 —— HTTPS 仍然不是可选项。
   另外登录失败节流按用户名计数，存在「用错误密码锁住别人账号」的可能（5 分钟）。

---

## 八、本轮纠正过的错误判断

记录在案，避免重复：

1. **「内存是瓶颈，靠 `MAX_TEAMS` 兜住」** —— 被实测否掉。20 个团队约 2 MB，团队几乎不占内存。
2. **把「先做哪个」写成「只能选一个」（两次）** —— 第一次把「HTTPS 与 Redis 限流」并列成
   或者关系；第二次把「Caddy 实测」与「systemd」并列。前者其实是顺序问题，后者里 Caddy 实测
   价值接近零（验的是别人的软件，且只在选 Caddy 时才有意义）。**该给判断的时候不要给菜单。**
3. **测量脚本把 0.0 当成数据打印** —— `GetProcessMemoryInfo` 调用失败但没检查返回值，
   于是打印出一排 `0.0 MB`。修法是设对 `restype/argtypes` 并强制校验返回值。

以下四条出自**线上落地与域名接入这一轮**：

4. **把 nginx 的 `ssl_certificate` 当成可以按 SNI 选证书** —— 两张证书写进一个 server 块，
   实测域名访问拿到了 IP 证书，比不改还糟（见 3.12）。**改完还误报了一次结论**（见下条）。
5. **探针抢在 `systemctl reload` 前面跑，连报两次假故障** —— 一次是「http 该 301 却返回 200」，
   一次是「两个 443 块也不生效」。两次都是 nginx 的旧 worker 还没换配置就接了请求。
   **reload 之后必须等几秒再验，否则测的是旧配置，结论是假的。**
6. **把「HTTP 200」当成「页面能用」** —— 声明前端「完整可用」时，只验证了 HTTP 层
   （`/health` 200、`/` 返回 24KB HTML、SSE 流式正常），**从没在浏览器里执行过一行 JS**。
   彼时页面完全不可用（3.10）。**验证必须覆盖到用户实际使用的那一层。**
7. **在一份自查清单里列了不存在的文件名**（`src/access/ratelimit.py`）—— 限流其实写在
   `server.py` 里，那个路径是我凭印象写的。**凡是写进脚本或文档的路径，先确认它存在。**

以下三条出自**账号密码登录这一轮**：

8. **把「重启服务」当成「会跑数据库迁移」** —— `init_db()` 是惰性的，只在第一次访问存储层
   时才执行。部署脚本里写的判据是「重启后检查新表」，于是表还没建，当场误判成迁移失败。
   **不要假设启动会做副作用；要验就显式触发一次（或发一个真实请求）。**
9. **断言失败时先怀疑了被测代码** —— 副本测试报了 3 项失败，逐个核对后**全是断言自己的
   问题**（吊销了 `t2` 却去查 `users.token`；拿「重复 `init_db` 后的数量」去比「中间新建过
   用户的数量」）。**断言失败的第一步是证明断言本身是对的。**（同一轮也确实抓到一个真
   bug —— 见 3.13 的「哨兵值复活」，所以这一步不是白跑的。）
10. **改 `users.token` 的写入语义时，漏掉了「每次 `init_db()` 都会读这一列」这条既有路径** ——
    于是吊销时写的哨兵值会在下次启动被当成有效凭证搬回 `tokens` 表。**改一个字段的语义，
    要先把所有读写它的路径列全，包括那些"看起来只是初始化"的路径。**

---

## 九、遗留项（承自 `docs/plan-review-archive.md`，多数未复核）

以下条目来自归档文档第五节，**本轮没有触碰，状态未复核**：

| 原编号 | 问题 | 备注 |
|--------|------|------|
| 5.5 | `short_term.py` 的 `ContextTruncation` 分支用 `OpenAITokenCounter`，会触发 tiktoken 词表下载而**永久卡死** | 该函数目前是死代码，但改动成本极低（换 `CharTokenCounter`） |
| 5.6 | `long_term.py` 的 docstring 仍写着 `both`，签名已不含 | 文档与代码不一致 |
| 5.7 | `mode="both"` 时不会追加记忆工具提示 | 将来允许 `both` 时会踩 |
| 5.8 | `cli.py` 的几个未使用导入、`--interactive` 参数解析后未使用等 | 参见归档文档 |
