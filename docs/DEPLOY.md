# 部署：HTTPS 与反向代理

公网部署前必读。核心一句话：**token 是明文凭证，没有 HTTPS 就等于没有认证。**

## 两种形态，选一种

| 形态 | 适用 | 应用侧改动 |
|------|------|-----------|
| **A. 反向代理 + TLS**（推荐） | 有域名、要对外 | 无 —— 保持 `HOST=127.0.0.1`，证书交给代理 |
| **B. 直连 HTTPS** | 内网/临时验证、没有代理 | 设 `SSL_CERTFILE` / `SSL_KEYFILE` |

前提都一样：`QDRANT_URL` 必须配（原因见文末「已知限制」）。

---

## 第 0 步：决定暴露方式（这决定要不要备案）

服务器在**大陆**时，**域名指向 80/443 必须完成 ICP 备案**，否则会被阻断。但有两条路可以立刻上线：

| 方式 | 备案 | 证书 | 适合 |
|------|------|------|------|
| **纯 IP + IP 证书** | 不需要 | Let's Encrypt IP 证书（有效期仅约 6 天，**必须自动续期**） | 立刻可用、自己或小范围使用 |
| **域名 + 普通证书** | 需要（1–3 周） | Let's Encrypt / 云厂商免费证书 | 对外提供、要一个能记住的地址 |

### 路线一：纯 IP + Let's Encrypt IP 证书（推荐先用这条）

Let's Encrypt 自 **2026-01** 起正式为**纯 IP**签发证书（与 6 天短有效期同时转 GA），
IPv4 / IPv6 都支持。这意味着**不需要域名、不需要备案**就能拿到浏览器信任的 HTTPS。

```bash
# 先确认能从这台机器连上 ACME 端点（大陆机房有时不稳）
curl -I https://acme-v02.api.letsencrypt.org/directory

# 必须用 snap 装, 不能用 apt: Ubuntu 22.04 的 certbot 是 1.21、24.04 是 2.11,
# 都远低于支持 --ip-address 所需的 5.3 (webroot 方式需要 5.4)。
# apt 装出来的版本会直接报 "no such option: --ip-address"。
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/bin/certbot
certbot --version            # 确认是 5.4 以上

# 注意：这个目录必须与 deploy/nginx.conf 里 /.well-known/acme-challenge/ 的 root 一致
sudo mkdir -p /var/www/certbot
# 顺序要求: webroot 校验需要 80 端口已经在服务这个目录,
# 所以要先让 nginx 以「只有 80 端口」的配置跑起来 (见「方案 A1」第 2 步的提示)。
sudo certbot certonly \
  --preferred-profile shortlived \
  --webroot --webroot-path /var/www/certbot \
  --ip-address <你的公网 IP>
```

证书落在 `/etc/letsencrypt/live/<你的公网 IP>/`。**certbot 目前还不能自动把 IP 证书装进
nginx**，要在 `deploy/nginx.conf` 里手动指定：

```nginx
ssl_certificate     /etc/letsencrypt/live/<你的公网 IP>/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/<你的公网 IP>/privkey.pem;
server_name         <你的公网 IP>;
```

三个必须知道的点：

- **有效期只有约 6 天，所以续期不是可选项，是运行前提。** 用 certbot 自带的 timer
  （`systemctl list-timers | grep certbot`）。
- **不要手动反复重签。** Let's Encrypt 对同一组标识符有「每周 5 张重复证书」的限制，
  手动猛签会把自己锁进限流里。
- IP 证书只解决 HTTPS：`server_name` 要写 IP，HTTP→HTTPS 的 301 也要指向 IP。

### 路线二：域名 + 备案

要一个能记住的地址、要对外提供，就走这条：买域名 → 在云厂商控制台提交备案（1–3 周）→
域名解析到本机 → `sudo certbot --nginx -d 你的域名`。
审核期间可以先用路线一跑起来，两条路不冲突。

---

## 方案 A1：Nginx + certbot

```bash
# 1) 应用照原样跑 —— 只监听本机，对外由 Nginx 负责
cp .env.example .env          # 填 DASHSCOPE_API_KEY
# .env 里确认这三项：
#   HOST=127.0.0.1
#   QDRANT_URL=http://127.0.0.1:6333
#   FORWARDED_ALLOW_IPS=127.0.0.1
python scripts/run_server.py

# 2) 装 Nginx 与 certbot
sudo apt install nginx certbot python3-certbot-nginx
sudo mkdir -p /var/www/certbot
sudo cp deploy/nginx.conf /etc/nginx/conf.d/agent.conf
sudo sed -i 's/agent.example.com/你的域名/g' /etc/nginx/conf.d/agent.conf
sudo nginx -t && sudo systemctl reload nginx

# 3) 签发证书（certbot 会自动改好 Nginx 里的证书路径）
sudo certbot --nginx -d 你的域名

# 4) 确认自动续期已生效
systemctl list-timers | grep certbot
```

`deploy/nginx.conf` 里有三处必须按你的环境改：`server_name`、证书路径、`proxy_pass`。

## 方案 A2：Caddy（配置最少）

Caddy 会**自动申请并续期** Let's Encrypt 证书，不需要 certbot，只要域名解析到本机、80/443 可达。

```bash
# 本地跑
caddy run --config deploy/Caddyfile

# 作为服务
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

只改一处：把 `agent.example.com` 换成你的域名。

---

## 方案 B：直连 HTTPS

没有反向代理时，让 uvicorn 自己终止 TLS：

```bash
# 有域名：用 certbot 只签证书，不装 Nginx
sudo certbot certonly --standalone -d 你的域名
# .env:
#   HOST=0.0.0.0
#   SSL_CERTFILE=/etc/letsencrypt/live/你的域名/fullchain.pem
#   SSL_KEYFILE=/etc/letsencrypt/live/你的域名/privkey.pem
python scripts/run_server.py
```

注意 `HOST` 要改成 `0.0.0.0`（否则只有本机能连），并且要做开机自启（systemd）。

## 本地/内网试 HTTPS（自签）

```bash
python scripts/gen_self_signed_cert.py --host 192.168.1.10
# 生成的证书在 data/certs/，已在 .gitignore 里
set SSL_CERTFILE=./data/certs/cert.pem      # Linux/macOS 用 export
set SSL_KEYFILE=./data/certs/key.pem
python scripts/run_server.py
```

自签证书**只用于验证**：浏览器不信任它，客户端得加 `-k` 或关掉校验 —— 那就等于绕过了 HTTPS 的意义。对外服务请用 Let's Encrypt。

---

## 为什么 SSE 必须特殊配置

`/api/chat/stream` 是 Server-Sent Events，靠「边算边推」工作。一轮协作要跑多次模型调用，可能好几分钟，中间会不断产生增量文本。

默认配置会毁掉它，原因有两个，都是**缓冲**：

1. **`proxy_buffering on`（Nginx 默认开）** —— 代理把响应体攒在内存里，前端看到的是「转圈几分钟，然后整段蹦出来」。必须 `proxy_buffering off`。
2. **压缩** —— gzip/br 为了压缩率也要攒数据。流式接口必须 `gzip off`（Caddy 里是不给该路径套 `encode`）。

另外两个容易踩的：

- **超时** —— 默认 60s 会把长对话掐断，所以要 `proxy_read_timeout 600s`（Caddy 是 `read_timeout`）。
- **HTTP/1.1** —— `proxy_http_version 1.1` + `proxy_set_header Connection ''`，否则长连接行为异常。

应用自己已经发了 `X-Accel-Buffering: no` 和 `Cache-Control: no-cache`，但**这不能替代代理侧配置**。

---

## 上线检查清单

- [ ] `.env` 里 `HOST=127.0.0.1`、`PORT=8000`，且 `QDRANT_URL` 已填
- [ ] `FORWARDED_ALLOW_IPS` 只填代理的 IP，**绝不填 `*`**（否则客户端可以伪造 IP）
- [ ] HTTPS 生效：`curl -I https://你的域名` 返回 200，`curl -I http://你的域名` 返回 301
- [ ] 未认证被挡住：`curl https://你的域名/api/sessions` 返回 401
- [ ] **SSE 是增量到达的**，不是最后一次性（见下面的验证命令）
- [ ] `data/` 有备份（里面有 `sessions.db` 和向量库，丢了就是全部用户记忆）
- [ ] 私钥不在仓库里（`.gitignore` 已挡 `data/certs/`、`*.pem`、`*.key`）

验证 SSE 是否真的在增量推送（每隔一行应该有明显时间差）：

```bash
TOKEN=$(curl -s -X POST https://你的域名/api/auth/register \
        -H 'Content-Type: application/json' -d '{"name":""}' | python -c 'import sys,json;print(json.load(sys.stdin)["token"])')

curl -N -X POST https://你的域名/api/chat/stream \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"message":"用三句话介绍你自己","session_id":"probe"}' \
  | while IFS= read -r line; do printf '%s  %s\n' "$(date +%T)" "$line"; done
```

时间戳如果全挤在最后，就是代理的缓冲没关掉。

---

## 已知限制（务必知道）

1. **必须单 worker**。限流计数、任务锁、团队缓存都是进程内的（`src/access/server.py` 里的 `_rate` / `_locks` / `_teams`）。多 worker 会带来三个问题：限流额度变成 N 倍、**同一个任务可能在两个 worker 里同时跑**（Leader 的记忆不是并发安全的）、每 worker 各建一份团队（N 倍 MCP 连接与内存）。
2. **本地文件版 Qdrant 单进程独占**。不配 `QDRANT_URL` 就只能是单进程，多 worker 直接起不来。
3. 好消息是：这个应用是 I/O 密集型的，并发靠 `asyncio`，**单 worker 就能同时服务很多用户**；多 worker 对「等模型返回」这种瓶颈帮助很小。真要扩，更可能是多机 + 反向代理。
4. **限流两层**：应用层是「每用户每分钟 N 次」，网关层是「每 IP 每秒 N 次」。两者互补，不是替代。
5. **无需配 CORS**：前端和 API 由同一个代理提供，同源。除非你将来把前端分域部署。

## 把代码弄到服务器上

```bash
sudo apt update
sudo apt install -y python3-venv git nginx

# 家目录不要直接用 /opt/agent: useradd -m 会往里写 .bashrc 等文件,
# 之后 git clone 到非空目录会直接失败。所以家目录另放, 应用目录单独建。
sudo useradd -r -m -d /home/agent -s /bin/bash agent
sudo mkdir -p /opt/agent
sudo chown agent:agent /opt/agent

# 必须指定分支! 这个仓库的默认分支是 main, 而 main 上没有本轮改动
# (认证 / 用户隔离 / deploy 目录)。clone 默认分支等于部署一个没有认证的版本。
sudo -u agent git clone -b multi-agent <你的仓库地址> /opt/agent

# 依赖接近 1.9 GB：走国内镜像，否则会非常慢
sudo -u agent python3 -m venv /opt/agent/.venv
sudo -u agent /opt/agent/.venv/bin/pip install \
  -i https://mirrors.cloud.tencent.com/pypi/simple \
  -r /opt/agent/requirements.txt

# 环境变量：单独填，不要用仓库里的 .env
sudo -u agent cp /opt/agent/.env.example /opt/agent/.env
sudo -u agent vi /opt/agent/.env       # 填 DASHSCOPE_API_KEY 等
sudo chmod 600 /opt/agent/.env         # 只有服务账号能读
```

**三个必须注意的点：**

1. **不要用仓库里的 `.env`。** 这个仓库是公开的，`.env` 曾被提交到 `main` 与 `multi-agent`
   两个分支。服务器的 `.env` 必须在服务器上单独填，并且只存在于服务器上。
2. **`skills/` 只有一部分进了版本库。** `.gitignore` 里有 `skills/`，但
   `skills/course-review/SKILL.md` 在该规则生效之前就加入了，所以仍被跟踪；而
   `skills/frontend-design` 没有。直接 clone 到服务器会**少一个 skill**，需要手动 `scp` 补齐。
   对照启动日志里的 `工具池就绪: ... Skill N 个` 就能看出少了几个。
3. **`QDRANT_URL` 只有要多 worker 时才需要填。** 单进程部署（这个应用的推荐形态，见「已知限制」第 1 条）用本地文件版 Qdrant 就够了，不必为此再在同一台机器上起一个 Qdrant 容器。上面第 2 条说的是「多 worker 的前提」，不是「上线的前提」。

## 服务守护（systemd）

`python scripts/run_server.py` 是个**前台进程**：SSH 一断就死、重启不会自己起来、崩了不会
自动拉起。上线要装成服务：

```bash
sudo cp deploy/agent.service /etc/systemd/system/agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now agent

systemctl status agent
journalctl -u agent -f          # 看日志
```

单元文件里 **`WorkingDirectory=` 不能写错** —— `src/config.py:9` 是 `load_dotenv()`（不带路径，
按当前工作目录找 `.env`），目录不对就找不到 `.env`，`check_api_key()` 会在启动时直接失败。

## 排错

| 现象 | 原因 |
|------|------|
| 502 Bad Gateway | 应用没起，或 `proxy_pass` 的端口与 `PORT` 不一致 |
| 转圈到结束才出结果 | 代理缓冲没关：`proxy_buffering` / gzip / `flush_interval` |
| 几分钟后连接断 | `proxy_read_timeout`（Nginx）或 `read_timeout`（Caddy）太小 |
| 前端一直 401 | localStorage 里的 token 失效了，清掉重新打开页面即可 |
| 日志里客户端 IP 全是 127.0.0.1 | `FORWARDED_ALLOW_IPS` 没包含代理地址 |
