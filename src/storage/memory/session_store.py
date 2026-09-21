"""
用户与会话（任务）存储 — SQLite

数据表：
  users        —— 用户。`username` / `password_hash` 为 NULL 表示匿名账号
                 （仍然只用 token，保持「打开即用、无需注册」的体验）。
  tokens       —— 凭证。一个用户可有多条 token（多设备各自登录/登出；
                 登出只删自己那一条，既不影响其他设备，也不删账号本身）。
  sessions     —— 一个会话 = 一个任务。主键是 (user_id, session_id)，
                 所以不同用户即使传同一个 session_id 也互不可见。
  messages     —— 对话历史，按 (user_id, session_id) 归属，支持游标分页。
  user_skills  —— 用户自建技能。**库是唯一事实来源**，`materialize_user_skills()`
                 把它物化成磁盘目录（agentscope 只认目录里的 SKILL.md）。

用户维度是隔离的根：长期记忆按 user_id 打 payload，会话按 user_id 归属，
任何查询都必须带上它。

只用标准库 sqlite3，不引入新依赖。方法都是同步阻塞的，调用方负责用
`asyncio.to_thread(...)` 包一层（见 src/access/server.py 与 hierarchical.py）。
"""
import json
import logging
import re
import secrets
import shutil
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from src.config import SESSIONS_DB, USER_SKILLS_DIR

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    TEXT PRIMARY KEY,
    token      TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    user_id    TEXT NOT NULL,
    session_id TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, session_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(user_id, session_id, id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, updated_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _db():
    """每次操作开一个短连接。

    sqlite3 的连接不能跨线程复用，而这些方法会从 asyncio 的线程池里被调用，
    所以不适合用一个长期连接。
    """
    SESSIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SESSIONS_DB)
    conn.row_factory = sqlite3.Row
    try:
        with conn:          # 正常退出提交，异常回滚
            yield conn
    finally:
        conn.close()


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """把 v1 的表（session 全局唯一，没有用户维度）迁到 v2。

    v1 的 sessions 主键是 id，且没有 user_id 列。旧数据统一挂到一个
    `legacy` 用户名下，保证不丢。
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
    if not cols or "user_id" in cols:
        return      # 表还不存在（全新库）或已经是新结构

    conn.executescript(
        "ALTER TABLE sessions RENAME TO sessions_v1;"
        "ALTER TABLE messages RENAME TO messages_v1;"
    )
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO sessions (user_id, session_id, title, created_at, updated_at) "
        "SELECT 'legacy', id, title, created_at, updated_at FROM sessions_v1"
    )
    conn.execute(
        "INSERT INTO messages (user_id, session_id, role, name, content, created_at) "
        "SELECT 'legacy', session_id, role, name, content, created_at "
        "FROM messages_v1 ORDER BY id"
    )
    conn.executescript("DROP TABLE sessions_v1; DROP TABLE messages_v1;")


_SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS tokens (
    token        TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    last_used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tokens_user ON tokens(user_id);
"""


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """v2：账号密码 + 多设备令牌。

    1. users 增加 `username` / `password_hash`；匿名用户这两列为 NULL，
       行为与改动前完全一致。
    2. **把存量 token 搬进 tokens 表** —— 老客户端 localStorage 里的 token
       必须继续可用，不能因为这次改动把现有用户踢下线。
    3. username 建**部分**唯一索引：只对非 NULL 生效。否则一堆匿名用户
       （username 都是 NULL）会被唯一约束互相冲突掉。
    4. users.token 列保留不动（它是 NOT NULL UNIQUE，且是历史数据）。
       认证从此只查 tokens 表，见 get_user_by_token。
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if cols:
        if "username" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
        if "password_hash" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")

    conn.executescript(_SCHEMA_V2)

    # 搬存量 token 是**一次性**动作，所以只在 tokens 表为空时做。
    # 如果每次启动都扫一遍 users.token，那么这一列里任何"之后才出现"的值
    # 都会被当成有效凭证重新插进来 —— 具体说，登出时写入的哨兵值
    # （见 revoke_token）会在下次重启时复活成一行可用 token。
    # 这个 bug 是在数据库副本上跑幂等性测试时抓到的。
    if conn.execute("SELECT 1 FROM tokens LIMIT 1").fetchone() is None:
        conn.execute(
            "INSERT OR IGNORE INTO tokens (token, user_id, created_at) "
            "SELECT token, user_id, created_at FROM users "
            "WHERE token IS NOT NULL AND token != ''"
        )

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username "
        "ON users(username) WHERE username IS NOT NULL"
    )


_SKILLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_skills (
    skill_id    TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_skills_slug
    ON user_skills(user_id, slug);
"""


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """v3：用户自建技能。

    正文存库（唯一事实来源），磁盘目录只是给 agentscope 用的**物化视图** ——
    它只认目录里的 SKILL.md。这样备份跟着 data/sessions.db 一起走，
    也不会出现「库里有、盘上没了」的漂移。
    """
    conn.executescript(_SKILLS_SCHEMA)


def init_db() -> None:
    """建表 + 迁移（幂等）。"""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        with _db() as conn:
            _migrate_v1(conn)
            conn.executescript(_SCHEMA)
            _migrate_v2(conn)
            _migrate_v3(conn)
        _initialized = True


# ── 用户自建技能 ──
#: 用户可见的技能目录名（slug）。只允许小写字母数字和横线 —— 它同时是磁盘目录名，
#: 所以从入口就要杜绝路径穿越（物化时会再校验一次）。
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
#: 路径片段的兜底校验（user_id / slug 用）。比 slug 宽松，但排除分隔符与 ..
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

MAX_SKILL_BODY = 20_000
MAX_SKILL_DESC = 500
MAX_SKILLS_PER_USER = 20


class SkillValidationError(ValueError):
    """技能字段不合法：slug 格式、长度、重名或数量超限。"""


def _safe_segment(value: str) -> str | None:
    """能安全地当路径名就返回它，否则 None。"""
    v = (value or "").strip()
    if v in {"", ".", ".."} or not _SEGMENT_RE.match(v):
        return None
    return v


def _validate_skill_fields(slug: str, name: str, description: str, body: str) -> None:
    if not _SLUG_RE.match(slug):
        raise SkillValidationError(
            "技能目录名只能是小写字母、数字或横线（1-40 位，且以字母或数字开头）"
        )
    if not name.strip():
        raise SkillValidationError("技能名称不能为空")
    if len(name) > 60:
        raise SkillValidationError("技能名称最长 60 字")
    if len(description) > MAX_SKILL_DESC:
        raise SkillValidationError(f"技能描述最长 {MAX_SKILL_DESC} 字")
    if not body.strip():
        raise SkillValidationError("技能正文不能为空")
    if len(body) > MAX_SKILL_BODY:
        raise SkillValidationError(f"技能正文最长 {MAX_SKILL_BODY} 字")


_SKILL_COLS = "skill_id, slug, name, description, body, created_at, updated_at"


def list_user_skills(user_id: str) -> list[dict]:
    """列出某个用户的技能。

    带上 body 是有意的：前端「编辑」要直接预填正文，否则用户改一个错字就得
    全文重打。列表接口本来就是这个用户在界面上唯一的数据来源。
    """
    init_db()
    with _db() as conn:
        rows = conn.execute(
            f"SELECT {_SKILL_COLS} FROM user_skills WHERE user_id = ? "
            "ORDER BY updated_at DESC, slug",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_user_skill(user_id: str, skill_id: str) -> dict | None:
    """取单个技能（含正文）。**按 user_id 过滤** —— 别人的 skill_id 一律查不到。"""
    init_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM user_skills WHERE user_id = ? AND skill_id = ?",
            (user_id, skill_id),
        ).fetchone()
    return dict(row) if row else None


def create_user_skill(
    user_id: str,
    slug: str,
    name: str,
    description: str = "",
    body: str = "",
) -> dict:
    """新建技能。slug 在同一用户下唯一。

    Raises:
        SkillValidationError: 字段不合法、slug 重名或超过数量上限
    """
    init_db()
    slug = (slug or "").strip().lower()
    name = (name or "").strip()
    description = (description or "").strip()
    _validate_skill_fields(slug, name, description, body)

    skill_id = uuid.uuid4().hex
    now = _now()
    with _db() as conn:
        n = conn.execute(
            "SELECT count(*) FROM user_skills WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        if n >= MAX_SKILLS_PER_USER:
            raise SkillValidationError(f"技能数量已达上限 {MAX_SKILLS_PER_USER}")
        if conn.execute(
            "SELECT 1 FROM user_skills WHERE user_id = ? AND slug = ?", (user_id, slug)
        ).fetchone():
            raise SkillValidationError(f"技能目录名 '{slug}' 已存在")
        conn.execute(
            "INSERT INTO user_skills "
            "(skill_id, user_id, slug, name, description, body, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (skill_id, user_id, slug, name, description, body, now, now),
        )
    return get_user_skill(user_id, skill_id) or {}


def update_user_skill(
    user_id: str,
    skill_id: str,
    name: str | None = None,
    description: str | None = None,
    body: str | None = None,
) -> dict | None:
    """改技能：只改传进来的字段。返回 None 表示这个技能不属于该用户。"""
    init_db()
    cur = get_user_skill(user_id, skill_id)
    if cur is None:
        return None

    new_name = cur["name"] if name is None else name.strip()
    new_desc = cur["description"] if description is None else (description or "").strip()
    new_body = cur["body"] if body is None else (body or "")
    _validate_skill_fields(cur["slug"], new_name, new_desc, new_body)

    with _db() as conn:
        conn.execute(
            "UPDATE user_skills SET name = ?, description = ?, body = ?, updated_at = ? "
            "WHERE user_id = ? AND skill_id = ?",
            (new_name, new_desc, new_body, _now(), user_id, skill_id),
        )
    return get_user_skill(user_id, skill_id)


def _remove_materialized_skill(user_id: str, slug: str) -> None:
    """把某个技能在磁盘上的物化目录删掉（尽力而为，失败只记日志）。

    正常路径下这活由 `materialize_user_skills()` 顺手做，但那只发生在装配团队时：
    删完技能却还没提问的话，盘上会留一个孤儿目录。它不会被注册（技能清单来自库），
    只是脏 —— 这里顺手清掉，省得看起来像"删不干净"。
    """
    safe_user, safe_slug = _safe_segment(user_id), _safe_segment(slug)
    if safe_user is None or safe_slug is None:
        return
    skill_dir = USER_SKILLS_DIR / safe_user / safe_slug
    try:
        if skill_dir.is_dir():
            shutil.rmtree(skill_dir, ignore_errors=True)
    except OSError as e:
        logger.warning("清理技能目录失败 %s/%s: %s", safe_user, safe_slug, e)


def delete_user_skill(user_id: str, skill_id: str) -> bool:
    """删技能。返回 False 表示这个技能不属于该用户（或不存在）。"""
    init_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT slug FROM user_skills WHERE user_id = ? AND skill_id = ?",
            (user_id, skill_id),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "DELETE FROM user_skills WHERE user_id = ? AND skill_id = ?",
            (user_id, skill_id),
        )
    _remove_materialized_skill(user_id, row[0])
    return True


def _render_skill_md(row: dict) -> str:
    """生成 SKILL.md 正文。

    `name` 必须等于 slug —— 清单里给模型的名字、它调 read_skill_file 时传的名字、
    目录名，三者必须一致，否则工具查不到技能。

    描述用 `json.dumps` 包成带引号的 YAML 标量：用户写的描述里一旦出现冒号或引号，
    不加引号就会把 frontmatter 解坏。
    """
    desc = " ".join((row["description"] or "").split()) or f"用户技能 {row['slug']}"
    return (
        "---\n"
        f"name: {json.dumps(row['slug'], ensure_ascii=False)}\n"
        f"description: {json.dumps(desc, ensure_ascii=False)}\n"
        "---\n\n"
        f"{(row['body'] or '').strip()}\n"
    )


def materialize_user_skills(user_id: str) -> list[str]:
    """把用户技能物化成磁盘目录，返回可直接交给 agentscope 的目录列表。

    每次装配团队时调用：**内容不一致才写、库里已删的目录才清理** —— 所以是幂等的，
    也不会因为并发装配互相删文件（同一用户的两个任务会同时装配）。

    这里是「库是唯一事实来源、磁盘只是视图」的落点。deleted 技能如果不清盘，
    它会继续被注册、继续生效 —— 那是删不掉的 bug。
    """
    init_db()
    safe_user = _safe_segment(user_id)
    if safe_user is None:
        logger.warning("user_id 不合法，跳过技能物化: %r", user_id)
        return []

    root = USER_SKILLS_DIR / safe_user
    root.mkdir(parents=True, exist_ok=True)

    with _db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT slug, name, description, body FROM user_skills "
                "WHERE user_id = ? ORDER BY slug",
                (user_id,),
            ).fetchall()
        ]

    kept: dict[str, str] = {}
    for row in rows:
        slug = _safe_segment(row["slug"])
        # 写入时已校验过，这里是第二道闸：宁可跳过也不越界
        if slug is None or not _SLUG_RE.match(slug):
            logger.warning("技能 slug 不合法，跳过: %r", row["slug"])
            continue
        content = _render_skill_md(row)
        skill_dir = root / slug
        skill_md = skill_dir / "SKILL.md"
        try:
            skill_dir.mkdir(parents=True, exist_ok=True)
            if not skill_md.is_file() or skill_md.read_text(encoding="utf-8") != content:
                skill_md.write_text(content, encoding="utf-8")
        except OSError as e:
            logger.warning("技能写入失败，跳过 %s: %s", slug, e)
            continue
        kept[slug] = str(skill_dir)

    try:
        for child in root.iterdir():
            if child.is_dir() and child.name not in kept:
                shutil.rmtree(child, ignore_errors=True)
    except OSError as e:
        logger.warning("清理过期技能目录失败: %s", e)

    return [kept[s] for s in sorted(kept)]


# ── 用户与凭证 ──
def _new_token() -> str:
    """新凭证。用 secrets（约 256 bit）而不是 uuid4 —— 凭证的熵越足越好。"""
    return secrets.token_urlsafe(32)


def _public_user(row: dict) -> dict:
    """抹掉不该出库的字段（password_hash），并补上 is_anonymous。"""
    user = {k: v for k, v in row.items() if k != "password_hash"}
    user["is_anonymous"] = not user.get("username")
    return user


def create_user(name: str = "") -> dict:
    """新建**匿名**用户并发放 token（保持「打开即用」，无需注册）。

    user_id 与 token 刻意分开：token 是凭证，user_id 是标识。长期记忆会把
    user_id 写进向量库的 payload，凭证不该出现在那里。

    注意：users.token 是历史列（NOT NULL UNIQUE），这里也要写一个值；
    认证实际只看 tokens 表。
    """
    init_db()
    user_id = uuid.uuid4().hex
    token = _new_token()
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO users (user_id, token, name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, token, name, now),
        )
        conn.execute(
            "INSERT INTO tokens (token, user_id, created_at, last_used_at) "
            "VALUES (?, ?, ?, ?)",
            (token, user_id, now, now),
        )
    return {
        "user_id": user_id,
        "token": token,
        "name": name,
        "created_at": now,
        "username": None,
        "is_anonymous": True,
    }


def create_user_with_credentials(
    username: str, password_hash: str, name: str = ""
) -> dict:
    """新建**具名**账号（有用户名与密码）。

    `username` 必须已由调用方归一化（`passwords.normalise_username`）。
    用户名重复时抛 sqlite3.IntegrityError —— 调用方负责转成 409。
    """
    init_db()
    user_id = uuid.uuid4().hex
    token = _new_token()
    now = _now()
    display = name or username
    with _db() as conn:
        conn.execute(
            "INSERT INTO users (user_id, token, name, created_at, username, password_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, token, display, now, username, password_hash),
        )
        conn.execute(
            "INSERT INTO tokens (token, user_id, created_at, last_used_at) "
            "VALUES (?, ?, ?, ?)",
            (token, user_id, now, now),
        )
    return {
        "user_id": user_id,
        "token": token,
        "name": display,
        "created_at": now,
        "username": username,
        "is_anonymous": False,
    }


def attach_credentials(user_id: str, username: str, password_hash: str) -> bool:
    """给一个**已存在**（通常是匿名）账号补上用户名与密码。

    这是「注册时带走当前历史」的实现：不新建空账号，而是把凭据绑到当前
    user_id 上，于是已经产生的会话与长期记忆全都跟着过来。

    条件里的 `username IS NULL` 是有意的：只允许匿名账号被绑一次，
    具名账号不能被再次覆盖（否则等于凭据可被改写）。
    """
    init_db()
    with _db() as conn:
        cur = conn.execute(
            "UPDATE users SET username = ?, password_hash = ?, name = ? "
            "WHERE user_id = ? AND username IS NULL",
            (username, password_hash, username, user_id),
        )
    return cur.rowcount > 0


def get_user_by_username(username: str) -> dict | None:
    """按用户名查用户（含 password_hash，供登录校验用）。"""
    if not username:
        return None
    init_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT user_id, name, created_at, username, password_hash "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def issue_token(user_id: str) -> str:
    """给已有账号再发一个 token（登录时调用，支持多设备并存）。"""
    init_db()
    token = _new_token()
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO tokens (token, user_id, created_at, last_used_at) "
            "VALUES (?, ?, ?, ?)",
            (token, user_id, now, now),
        )
    return token


def get_user_by_token(token: str) -> dict | None:
    """按 token 查用户（认证入口）。token 无效返回 None。

    顺带更新 last_used_at，供界面展示「上次活跃」。
    """
    if not token:
        return None
    init_db()
    now = _now()
    with _db() as conn:
        row = conn.execute(
            "SELECT u.user_id, u.name, u.created_at, u.username "
            "FROM tokens t JOIN users u ON u.user_id = t.user_id "
            "WHERE t.token = ?",
            (token,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE tokens SET last_used_at = ? WHERE token = ?", (now, token))
    return _public_user(dict(row))


def revoke_token(token: str) -> bool:
    """吊销 token。

    只删 tokens 表里这一条 —— 同用户的其他设备不受影响，账号与历史也都还在。
    （改动前这里是 `DELETE FROM users`，等于登出就把账号删了，是个隐患。）
    """
    init_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT user_id FROM tokens WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
        # users.token 是历史列，认证已不看它；抹掉以免留下一个「看起来还能用」的值
        conn.execute(
            "UPDATE users SET token = ? WHERE user_id = ? AND token = ?",
            ("revoked-" + secrets.token_hex(8), row["user_id"], token),
        )
    return True


# ── 会话（任务）──
def ensure_session(user_id: str, session_id: str, title: str = "") -> dict:
    """确保会话存在（不存在则建），返回会话信息。"""
    init_db()
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, session_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, session_id) DO NOTHING",
            (user_id, session_id, title or session_id, now, now),
        )
    return get_session(user_id, session_id)


def get_session(user_id: str, session_id: str) -> dict | None:
    """取会话信息（含消息条数）。"""
    init_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM messages m "
            "            WHERE m.user_id = s.user_id AND m.session_id = s.session_id) "
            "       AS messages "
            "FROM sessions s WHERE s.user_id = ? AND s.session_id = ?",
            (user_id, session_id),
        ).fetchone()
    return dict(row) if row else None


def session_exists(user_id: str, session_id: str) -> bool:
    """该用户下是否已有这个任务。"""
    init_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ).fetchone()
    return row is not None


def count_sessions(user_id: str) -> int:
    """该用户的任务数（用于配额）。"""
    init_db()
    with _db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,)
        ).fetchone()[0]


def list_sessions(user_id: str, limit: int = 100) -> list[dict]:
    """列出该用户的所有任务，最近活跃的排在前面。"""
    init_db()
    with _db() as conn:
        rows = conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM messages m "
            "            WHERE m.user_id = s.user_id AND m.session_id = s.session_id) "
            "       AS messages "
            "FROM sessions s WHERE s.user_id = ? "
            "ORDER BY s.updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def rename_session(user_id: str, session_id: str, title: str) -> dict | None:
    """改任务名。"""
    init_db()
    with _db() as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? "
            "WHERE user_id = ? AND session_id = ?",
            (title, _now(), user_id, session_id),
        )
    return get_session(user_id, session_id)


def delete_session(user_id: str, session_id: str) -> None:
    """删除该用户下的任务及其全部历史。"""
    init_db()
    with _db() as conn:
        conn.execute(
            "DELETE FROM messages WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )


def append_turn(user_id: str, session_id: str, user_text: str, agent_text: str) -> None:
    """记录一轮对话（用户提问 + Leader 回复）。"""
    init_db()
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, session_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, session_id) DO UPDATE SET updated_at = excluded.updated_at",
            (user_id, session_id, session_id, now, now),
        )
        if user_text:
            conn.execute(
                "INSERT INTO messages (user_id, session_id, role, name, content, created_at) "
                "VALUES (?, ?, 'user', 'user', ?, ?)",
                (user_id, session_id, user_text, now),
            )
        if agent_text:
            conn.execute(
                "INSERT INTO messages (user_id, session_id, role, name, content, created_at) "
                "VALUES (?, ?, 'assistant', 'Project Leader', ?, ?)",
                (user_id, session_id, agent_text, now),
            )


def page_messages(
    user_id: str, session_id: str, limit: int = 20, before: int | None = None
) -> dict:
    """按游标分页读取对话历史。

    从最新往旧翻：不传 `before` 取最新一页；要更早的一页，就把上一页返回的
    `next_cursor` 传进 `before`。返回的 `messages` 已排成时间正序，前端可直接渲染。

    Args:
        user_id: 用户 ID（隔离的根本）
        session_id: 会话（任务）ID
        limit: 本页最多返回几条
        before: 游标，只取 id 小于它的消息

    Returns:
        {"messages": [...], "next_cursor": int | None, "total": int}
    """
    init_db()
    limit = max(1, min(limit, 200))
    with _db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ).fetchone()[0]
        if before is None:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id = ? AND session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (user_id, session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id = ? AND session_id = ? AND id < ? "
                "ORDER BY id DESC LIMIT ?",
                (user_id, session_id, before, limit),
            ).fetchall()

    rows = list(reversed(rows))          # DESC 取的是最新 N 条，翻回时间正序
    next_cursor = rows[0]["id"] if len(rows) == limit else None
    return {
        "messages": [dict(r) for r in rows],
        "next_cursor": next_cursor,
        "total": total,
    }


def recent_turns(user_id: str, session_id: str, turns: int) -> list[dict]:
    """取最近 N 轮对话（turns×2 条消息，时间正序）。

    用于重新打开任务时把上下文回放给 Leader。
    """
    init_db()
    if turns <= 0:
        return []
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE user_id = ? AND session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, session_id, turns * 2),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]
