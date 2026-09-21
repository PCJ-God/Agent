"""
接入层 - FastAPI Server
提供 REST API 和原生 HTML 前端

四层架构:
  接入层 (本模块) → 调度层 (HierarchicalTeam) → 执行层 (Agents + MCP + Skills) → 存储层 (Memory)
"""
import asyncio
import json
import logging
import sqlite3
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from src.access import passwords
from src.access.auth import bearer_token, current_user
from src.config import (
    FORWARDED_ALLOW_IPS,
    HOST,
    MAX_SESSIONS_PER_USER,
    MAX_TEAMS,
    PORT,
    RATE_LIMIT_PER_MINUTE,
    SSL_CERTFILE,
    SSL_KEYFILE,
    check_api_key,
    setup_logging,
)
from src.execution.tools.skill_files import frontmatter_meta
from src.execution.tools.tool_manager import (
    create_mcp_client,
    list_skill_dirs,
    mcp_server_info,
)
from src.orchestration.hierarchical import HierarchicalTeam
from src.storage.memory.session_store import (
    SkillValidationError,
    attach_credentials,
    count_sessions,
    create_user,
    create_user_skill,
    create_user_with_credentials,
    delete_session,
    delete_user_skill,
    ensure_session,
    get_user_by_username,
    issue_token,
    list_sessions,
    list_user_skills,
    page_messages,
    revoke_token,
    session_exists,
    update_user_skill,
)

logger = logging.getLogger(__name__)


# ── 数据模型 ──
DEFAULT_SESSION = "default"


class RegisterRequest(BaseModel):
    name: str = Field(default="", description="可选的名字，便于识别")
    username: str = Field(
        default="", description="用户名；与 password 一起给出即为具名账号"
    )
    password: str = Field(
        default="", description="密码（至少 8 位）；留空则创建匿名账号"
    )


class CredentialsRequest(BaseModel):
    username: str = Field(description="用户名（不区分大小写）")
    password: str = Field(description="密码")


class UserInfo(BaseModel):
    user_id: str = Field(description="用户 ID（长期记忆按它隔离）")
    name: str = ""
    created_at: str = ""
    username: Optional[str] = Field(
        default=None, description="具名账号的用户名；匿名为 null"
    )
    is_anonymous: bool = Field(
        default=True, description="是否尚未绑定用户名密码（匿名账号）"
    )


class RegisterResponse(UserInfo):
    token: str = Field(description="凭证。之后用 Authorization: Bearer <token> 访问")


class ChatRequest(BaseModel):
    message: str = Field(description="用户问题")
    session_id: str = Field(
        default=DEFAULT_SESSION,
        description="任务 ID。同一用户下不同任务的记忆互相隔离；跨用户天然隔离",
    )


class SkillRequest(BaseModel):
    slug: str = Field(description="技能目录名：小写字母/数字/横线，1-40 位")
    name: str = Field(description="技能名称（展示用）")
    description: str = Field(default="", description="一句话说明它解决什么问题")
    body: str = Field(description="技能正文（Markdown）。模型会在需要时按需读取它")


class SkillPatchRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None


class SkillInfo(BaseModel):
    skill_id: str = Field(default="", description="用户技能 ID；内置技能为空")
    slug: str = Field(description="技能目录名。也是模型调 read_skill_file 时用的名字")
    name: str = ""
    description: str = ""
    body: str = Field(
        default="",
        description="技能正文。列表里一并返回，前端编辑时直接预填，省一次请求",
    )
    builtin: bool = Field(default=False, description="内置技能：只读，不能改或删")
    created_at: str = ""
    updated_at: str = ""


class McpStatus(BaseModel):
    status: str = Field(description="connected / unreachable / unavailable")
    name: str = ""
    transport: str = ""
    host: str = Field(default="", description="只有主机名：不带密钥，也不给完整 URL")
    tools: list[str] = Field(default_factory=list, description="实测列出来的工具名")
    detail: str = Field(default="", description="失败原因；成功时为空")


class AgentResponse(BaseModel):
    success: bool = Field(description="是否成功执行")
    response: str = Field(description="Agent 回复内容")
    error: Optional[str] = Field(default=None, description="错误信息")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class HealthResponse(BaseModel):
    status: str = "ok"
    mcp: str = "disconnected"
    sessions: int = 0


# ── 会话（任务）管理 ──
# 缓存键是 (user_id, session_id)：同一个 session_id 在不同用户下是两个
# 互不相干的团队。锁也按这个键分 —— 不同用户、不同任务都能并行推进。
_teams: "OrderedDict[tuple[str, str], HierarchicalTeam]" = OrderedDict()
_locks: dict[tuple[str, str], asyncio.Lock] = {}
_registry_lock = asyncio.Lock()      # 只保护上面两个容器，不参与对话本身
_rate: dict[str, list[float]] = {}   # user_id -> 最近一分钟的请求时间戳


def session_lock(key: tuple[str, str]) -> asyncio.Lock:
    """取该任务自己的锁。不同任务互不阻塞。"""
    lock = _locks.get(key)
    if lock is None:
        lock = _locks[key] = asyncio.Lock()
    return lock


def _evict_locked(exclude: tuple[str, str]) -> None:
    """超出 MAX_TEAMS 时按 LRU 淘汰空闲团队。

    正在对话的（锁被持有）不踢。历史都在 SQLite 里，被淘汰的任务下次访问
    会重新装配并回放上下文。
    """
    while len(_teams) > MAX_TEAMS:
        for key in list(_teams.keys()):          # OrderedDict：最久未用的在前
            if key != exclude and not session_lock(key).locked():
                _teams.pop(key, None)
                break
        else:
            return      # 全都在忙，暂时超限


async def invalidate_user_teams(user_id: str) -> int:
    """丢掉某个用户的所有缓存团队，返回丢掉的数量。

    用户改了自己的技能之后必须调用 —— 技能是在**装配**时物化进工具池的，
    缓存里的团队不会自己更新。正在对话的（锁被持有）不动：让它跑完，
    下次访问自然会重建。

    重建是安全且被设计过的路径：历史都在 SQLite 里，会按 HISTORY_REPLAY_TURNS
    回放，LRU 淘汰走的也是同一条路。
    """
    dropped = 0
    async with _registry_lock:
        for key in [k for k in _teams if k[0] == user_id]:
            if session_lock(key).locked():
                continue
            _teams.pop(key, None)
            dropped += 1
    return dropped


async def get_team(user_id: str, session_id: str) -> HierarchicalTeam:
    """按 (用户, 任务) 获取（惰性装配的）团队。"""
    key = (user_id, session_id)
    async with _registry_lock:
        team = _teams.get(key)
        if team is not None:
            _teams.move_to_end(key)
            return team
        # 新任务先查配额；已存在的任务不受影响
        if not await asyncio.to_thread(session_exists, user_id, session_id):
            used = await asyncio.to_thread(count_sessions, user_id)
            if used >= MAX_SESSIONS_PER_USER:
                raise HTTPException(
                    status_code=429,
                    detail=f"任务数已达上限 {MAX_SESSIONS_PER_USER}，请先删除不再需要的任务",
                )

    # 装配很慢（连 MCP、抓工具、建三个 Agent），放到锁外做 ——
    # 不能让一个用户的首次请求把所有用户都堵住。
    team = await HierarchicalTeam.create(session_id=session_id, user_id=user_id)
    async with _registry_lock:
        existing = _teams.setdefault(key, team)
        _teams.move_to_end(key)
        _evict_locked(key)
        return existing


def check_rate_limit(user_id: str) -> None:
    """每用户每分钟最多 RATE_LIMIT_PER_MINUTE 次对话请求（<=0 表示关闭）。"""
    if RATE_LIMIT_PER_MINUTE <= 0:
        return
    now = time.monotonic()
    hits = [t for t in _rate.get(user_id, []) if now - t < 60.0]
    if len(hits) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁（每分钟最多 {RATE_LIMIT_PER_MINUTE} 次），请稍后再试",
        )
    hits.append(now)
    _rate[user_id] = hits


def mcp_status() -> str:
    """MCP 连接状态（供 /health 展示）。"""
    if not _teams:
        return "initializing"
    team = next(iter(_teams.values()))
    return "connected" if team.mcp_client is not None else "unavailable"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时只校验配置。

    多用户场景下没有「默认会话」这回事（团队按 (用户, 任务) 装配），而且每个
    团队自带 MCP 客户端，预热一个并不能加速别人的首次请求 —— 所以改为按需装配。
    """
    check_api_key()
    yield


app = FastAPI(title="Agent API — Hierarchical Mode", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查（公开，不含任何用户数据）。"""
    return HealthResponse(status="ok", mcp=mcp_status(), sessions=len(_teams))


# ── 认证 ──
# 两条拿到 token 的路：匿名（register 不带凭据，打开即用）与具名
# （register 带凭据直接建号 / login 用密码换 token）。
#
# 登录失败节流：scrypt 已把单次尝试压到 ~40ms，但仅靠它挡不住针对弱密码的
# 在线爆破。这里按用户名记失败次数，超限短暂拒绝（进程内计数；本项目单进程，
# 多 worker 时各算各的，仍能显著抬高爆破成本）。
#
# 取舍：按用户名计数意味着攻击者可以用错误密码把某个已知账号短暂锁住。
# 对当前场景（公网演示、账号数少）可接受；更稳妥要「账号 + 来源 IP」双维度，
# 那需要 nginx 传真实 IP（见 deploy/nginx.conf）。
_LOGIN_FAILS: dict[str, list] = {}      # username -> [失败次数, 窗口起点]
_LOGIN_WINDOW = 300.0                   # 统计窗口（秒）
_LOGIN_MAX_FAILS = 8                    # 窗口内允许的失败次数
_LOGIN_MAX_KEYS = 2000                  # 上限，避免被随机用户名撑爆内存


def _login_blocked(username: str) -> bool:
    """该用户名在当前窗口内是否已被节流。"""
    rec = _LOGIN_FAILS.get(username)
    if rec is None:
        return False
    count, start = rec
    if time.time() - start >= _LOGIN_WINDOW:
        _LOGIN_FAILS.pop(username, None)    # 窗口过了，重新计数
        return False
    return count >= _LOGIN_MAX_FAILS


def _note_login_failure(username: str) -> None:
    """记一次登录失败（登录成功时由调用方清掉）。"""
    if len(_LOGIN_FAILS) >= _LOGIN_MAX_KEYS:
        _LOGIN_FAILS.clear()                # 被随机用户名刷爆时整体重置
    now = time.time()
    count, start = _LOGIN_FAILS.get(username, (0, now))
    if now - start >= _LOGIN_WINDOW:
        count, start = 0, now
    _LOGIN_FAILS[username] = [count + 1, start]


@app.post("/api/auth/register", response_model=RegisterResponse)
async def api_register(req: RegisterRequest):
    """注册并发放 token。

    - 不给 username/password：建**匿名**账号（保持「打开即用」）
    - 给了 username/password：建**具名**账号，之后可跨设备用密码登录

    客户端保存 token，之后所有请求带 `Authorization: Bearer <token>`。
    """
    if not (req.username or req.password):
        return await asyncio.to_thread(create_user, req.name)

    if err := passwords.username_error(req.username):
        raise HTTPException(status_code=400, detail=err)
    if err := passwords.password_error(req.password):
        raise HTTPException(status_code=400, detail=err)

    # scrypt 要几十毫秒，放线程池算，别卡住事件循环
    pwd_hash = await asyncio.to_thread(passwords.hash_password, req.password)
    try:
        return await asyncio.to_thread(
            create_user_with_credentials,
            passwords.normalise_username(req.username),
            pwd_hash,
            req.name,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="用户名已被占用")


@app.post("/api/auth/login", response_model=RegisterResponse)
async def api_login(req: CredentialsRequest):
    """用用户名 + 密码登录，换一个**新的** token。

    每次登录发新 token，所以可以多设备同时登录：不会把已登录的设备踢下线，
    登出也只影响当前这一个 token。
    """
    username = passwords.normalise_username(req.username)
    if _login_blocked(username):
        raise HTTPException(
            status_code=429,
            detail=f"登录失败次数过多，请 {int(_LOGIN_WINDOW / 60)} 分钟后再试",
        )

    row = await asyncio.to_thread(get_user_by_username, username)
    if row is None or not row.get("password_hash"):
        # 账号不存在时也烧掉一次 scrypt 的时间，否则响应快慢能被用来枚举用户名
        _note_login_failure(username)
        await asyncio.to_thread(passwords.burn_time)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    ok = await asyncio.to_thread(
        passwords.verify_password, req.password, row["password_hash"]
    )
    if not ok:
        _note_login_failure(username)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    _LOGIN_FAILS.pop(username, None)
    token = await asyncio.to_thread(issue_token, row["user_id"])
    return RegisterResponse(
        user_id=row["user_id"],
        name=row["name"],
        created_at=row["created_at"],
        username=row["username"],
        is_anonymous=False,
        token=token,
    )


@app.post("/api/auth/bind", response_model=UserInfo)
async def api_bind(req: CredentialsRequest, user: dict = Depends(current_user)):
    """给**当前匿名账号**补上用户名 + 密码，已有历史原样带走。

    为什么不是「新建账号再搬历史」：那要跨 sessions / messages / 向量库三套
    存储做复制，任何一步失败都会留下半迁移状态。直接把凭据绑到现有 user_id
    上，历史天然就在原地。

    绑定后当前 token 仍有效（还是同一个 user_id），但之后就能用密码在别的
    设备登录、看到同一份历史。
    """
    if err := passwords.username_error(req.username):
        raise HTTPException(status_code=400, detail=err)
    if err := passwords.password_error(req.password):
        raise HTTPException(status_code=400, detail=err)

    username = passwords.normalise_username(req.username)
    pwd_hash = await asyncio.to_thread(passwords.hash_password, req.password)
    try:
        ok = await asyncio.to_thread(
            attach_credentials, user["user_id"], username, pwd_hash
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="用户名已被占用")
    if not ok:
        raise HTTPException(status_code=409, detail="当前账号已绑定用户名，不能重复绑定")
    # attach_credentials 会把展示名一并改成用户名，这里与库里保持一致
    return {**user, "name": username, "username": username, "is_anonymous": False}


@app.post("/api/auth/logout")
async def api_logout(token: str = Depends(bearer_token)):
    """吊销当前 token。

    只吊销这一个：同账号其他设备的登录不受影响，账号与历史也都还在
    （彻底删号是另一件事）。
    """
    if not await asyncio.to_thread(revoke_token, token):
        raise HTTPException(status_code=401, detail="token 无效或已吊销")
    return {"ok": True}


@app.get("/api/auth/me", response_model=UserInfo)
async def api_me(user: dict = Depends(current_user)):
    """校验 token 并返回当前用户（含是否已绑定用户名密码）。"""
    return user


@app.post("/api/chat", response_model=AgentResponse)
async def chat(req: ChatRequest, user: dict = Depends(current_user)):
    if not req.message:
        return AgentResponse(success=False, response="", error="消息不能为空")

    try:
        check_rate_limit(user["user_id"])
        key = (user["user_id"], req.session_id)
        team = await get_team(*key)
        # 任务内串行：Leader 的 InMemoryMemory 不是并发安全的
        async with session_lock(key):
            result = await team.chat(req.message)
        return AgentResponse(success=True, response=result)
    except HTTPException as e:
        return AgentResponse(success=False, response="", error=e.detail)
    except Exception as e:
        return AgentResponse(success=False, response="", error=str(e))


# ── 会话（任务）与历史 ──
class SessionInfo(BaseModel):
    session_id: str = Field(description="任务 ID")
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    messages: int = Field(default=0, description="该任务已有的消息条数")


class CreateSessionRequest(BaseModel):
    session_id: str = Field(default="", description="任务 ID；留空则自动生成")
    title: str = Field(default="", description="任务名称")


class MessageItem(BaseModel):
    id: int = Field(description="消息 ID，同时用作分页游标")
    role: str
    name: str = ""
    content: str
    created_at: str = ""


class MessagePage(BaseModel):
    session_id: str
    messages: list[MessageItem] = Field(description="按时间正序，可直接渲染")
    next_cursor: Optional[int] = Field(
        default=None,
        description="取更早一页时传给 before=；null 表示已经到头",
    )
    total: int = 0


@app.get("/api/sessions", response_model=list[SessionInfo])
async def api_list_sessions(user: dict = Depends(current_user)):
    """列出当前用户的所有任务（最近活跃的在前）。"""
    return await asyncio.to_thread(list_sessions, user["user_id"])


@app.post("/api/sessions", response_model=SessionInfo)
async def api_create_session(
    req: CreateSessionRequest, user: dict = Depends(current_user)
):
    """新建一个任务。"""
    user_id = user["user_id"]
    if await asyncio.to_thread(count_sessions, user_id) >= MAX_SESSIONS_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"任务数已达上限 {MAX_SESSIONS_PER_USER}，请先删除不再需要的任务",
        )
    session_id = req.session_id.strip() or f"task-{uuid.uuid4().hex[:8]}"
    return await asyncio.to_thread(ensure_session, user_id, session_id, req.title)


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str, user: dict = Depends(current_user)):
    """删除任务及其历史。"""
    key = (user["user_id"], session_id)
    await asyncio.to_thread(delete_session, *key)
    async with _registry_lock:
        _teams.pop(key, None)
        _locks.pop(key, None)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/messages", response_model=MessagePage)
async def api_session_messages(
    session_id: str,
    user: dict = Depends(current_user),
    limit: int = 20,
    before: Optional[int] = None,
):
    """分页读取某个任务的对话历史（从最新往旧翻）。"""
    page = await asyncio.to_thread(
        page_messages, user["user_id"], session_id, limit, before
    )
    return MessagePage(session_id=session_id, **page)


# ── 流式对话 (SSE) ──
_STREAM_DONE = object()


def _sse(payload: dict) -> str:
    """把一条数据编码成 SSE 帧。"""
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, user: dict = Depends(current_user)):
    """流式对话: 把三个 Agent 的输出实时推给前端 (Server-Sent Events)。

    与 /api/chat 的区别: 后者要等整轮协作结束后一次性返回，
    本端点在整个执行过程中持续推送增量文本。
    """
    if not req.message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    check_rate_limit(user["user_id"])
    key = (user["user_id"], req.session_id)
    lock = session_lock(key)
    if lock.locked():
        raise HTTPException(
            status_code=409,
            detail=f"任务 {req.session_id} 已有对话正在进行，请稍后再试或换一个任务",
        )

    team = await get_team(*key)
    queue: asyncio.Queue = asyncio.Queue()   # 不设上限，避免 Agent 阻塞在 put()
    team.enable_streaming(queue)
    await lock.acquire()

    async def run_chat():
        try:
            await queue.put((_STREAM_DONE, await team.chat(req.message)))
        except Exception as e:
            await queue.put((_STREAM_DONE, e))

    async def event_stream():
        task = asyncio.create_task(run_chat())
        sent: dict[str, int] = {}   # msg.id -> 已发送的字符数
        try:
            while True:
                item = await queue.get()
                if item[0] is _STREAM_DONE:
                    payload = item[1]
                    if isinstance(payload, Exception):
                        yield _sse({"type": "error", "error": str(payload)})
                    else:
                        yield _sse({"type": "done", "response": payload})
                    break

                msg, last, _speech = item
                text = msg.get_text_content() or ""
                offset = sent.get(msg.id, 0)
                if len(text) <= offset:
                    continue
                sent[msg.id] = len(text)
                yield _sse({
                    "type": "chunk",
                    "id": msg.id,
                    "name": msg.name,
                    "text": text[offset:],
                    "last": last,
                })
        finally:
            if not task.done():
                task.cancel()
            team.disable_streaming()
            lock.release()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── 前端静态文件 ──
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── 技能：内置（只读）+ 用户自建 ──
def _skill_info(row: dict, builtin: bool = False) -> SkillInfo:
    return SkillInfo(
        skill_id=row.get("skill_id", ""),
        slug=row["slug"],
        name=row.get("name") or row["slug"],
        description=row.get("description", ""),
        body=row.get("body", ""),
        builtin=builtin,
        created_at=row.get("created_at", ""),
        updated_at=row.get("updated_at", ""),
    )


@app.get("/api/skills", response_model=list[SkillInfo])
async def api_list_skills(user: dict = Depends(current_user)):
    """列出当前可用的技能：内置的（只读）+ 自己建的。"""
    builtin: list[SkillInfo] = []
    for d in list_skill_dirs():
        path = Path(d)
        meta = frontmatter_meta(path)
        builtin.append(
            SkillInfo(
                slug=path.name,
                name=meta.get("name") or path.name,
                description=meta.get("description", ""),
                builtin=True,
            )
        )
    mine = [
        _skill_info(row)
        for row in await asyncio.to_thread(list_user_skills, user["user_id"])
    ]
    return builtin + mine


@app.post("/api/skills", response_model=SkillInfo, status_code=201)
async def api_create_skill(req: SkillRequest, user: dict = Depends(current_user)):
    """新建用户技能，**保存即生效**。

    这里会让该用户所有空闲的缓存团队失效，下次提问时重新装配、把新技能物化进
    工具池。历史都在 SQLite 里，重建不丢上下文。
    """
    try:
        row = await asyncio.to_thread(
            create_user_skill,
            user["user_id"],
            req.slug,
            req.name,
            req.description,
            req.body,
        )
    except SkillValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="技能目录名已存在")

    dropped = await invalidate_user_teams(user["user_id"])
    logger.info(
        "技能已创建: user=%s slug=%s 失效团队=%d",
        user["user_id"][:8],
        row["slug"],
        dropped,
    )
    return _skill_info(row)


@app.put("/api/skills/{skill_id}", response_model=SkillInfo)
async def api_update_skill(
    skill_id: str, req: SkillPatchRequest, user: dict = Depends(current_user)
):
    """改自己的技能（只改传进来的字段）。"""
    try:
        row = await asyncio.to_thread(
            update_user_skill,
            user["user_id"],
            skill_id,
            req.name,
            req.description,
            req.body,
        )
    except SkillValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="技能不存在")
    await invalidate_user_teams(user["user_id"])
    return _skill_info(row)


@app.delete("/api/skills/{skill_id}")
async def api_delete_skill(skill_id: str, user: dict = Depends(current_user)):
    """删自己的技能。内置技能不在库里，所以删不到（返回 404）。"""
    ok = await asyncio.to_thread(delete_user_skill, user["user_id"], skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    await invalidate_user_teams(user["user_id"])
    return {"ok": True}


@app.get("/api/mcp", response_model=McpStatus)
async def api_mcp_status(user: dict = Depends(current_user)):
    """MCP 现状：配的是哪个服务、通不通、能用哪些工具。

    状态是**实测**的，不读 /health 里那个字段 —— 后者取自"已经装配过的团队"，
    进程刚重启、还没人提问时它必然显示 initializing，把"MCP 没连上"和
    "还没人用过"混成同一句话。所以这里真的建一次客户端、列一次工具。

    刻意只读：支持"自己添加 MCP 服务器"意味着要保存第三方 token，并允许 Agent
    向任意地址发起请求 —— 那是另一件事，也得先定好谁能加、加到谁名下。
    """
    info = mcp_server_info()
    client = await create_mcp_client()
    if client is None:
        return McpStatus(status="unavailable", detail="客户端创建失败", **info)

    try:
        tools = await asyncio.wait_for(client.list_tools(), timeout=10)
    except asyncio.TimeoutError:
        return McpStatus(status="unreachable", detail="10 秒内没有响应", **info)
    except Exception as e:
        # 网络 / DNS / 鉴权失败都归到这里；截断一下，避免把整段响应体带回前端
        reason = f"{type(e).__name__}: {e}"[:300]
        return McpStatus(status="unreachable", detail=reason, **info)

    return McpStatus(status="connected", tools=[t.name for t in tools], **info)


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


def run():
    """启动服务。

    两种部署形态：
      - 挂反向代理（推荐）：只监听 127.0.0.1，TLS 由代理终止
      - 直连 HTTPS：配 SSL_CERTFILE / SSL_KEYFILE
    """
    import uvicorn

    setup_logging()
    kwargs: dict = {}
    if SSL_CERTFILE and SSL_KEYFILE:
        kwargs.update(ssl_certfile=SSL_CERTFILE, ssl_keyfile=SSL_KEYFILE)
        logger.info("直连 HTTPS: https://%s:%s", HOST, PORT)
    else:
        logger.info("HTTP 监听 %s:%s（TLS 交给反向代理）", HOST, PORT)

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        # 相信反向代理发来的 X-Forwarded-For / X-Forwarded-Proto：
        # 否则日志里全是代理的 IP，客户端 IP 就查不出来了。
        proxy_headers=True,
        forwarded_allow_ips=FORWARDED_ALLOW_IPS,
        **kwargs,
    )


if __name__ == "__main__":
    run()