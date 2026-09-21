"""
用户与会话（任务）存储 — SQLite

两层数据：
  users      —— 用户 + 凭证。token 是 uuid4，客户端用它换身份。
  sessions   —— 一个会话 = 一个任务。主键是 (user_id, session_id)，
               所以不同用户即使传同一个 session_id 也互不可见。
  messages   —— 对话历史，按 (user_id, session_id) 归属，支持游标分页。

用户维度是隔离的根：长期记忆按 user_id 打 payload，会话按 user_id 归属，
任何查询都必须带上它。

只用标准库 sqlite3，不引入新依赖。方法都是同步阻塞的，调用方负责用
`asyncio.to_thread(...)` 包一层（见 src/access/server.py 与 hierarchical.py）。
"""
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from src.config import SESSIONS_DB

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


def init_db() -> None:
    """建表 + 迁移（幂等）。"""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        with _db() as conn:
            _migrate_v1(conn)
            conn.executescript(_SCHEMA)
        _initialized = True


# ── 用户与凭证 ──
def create_user(name: str = "") -> dict:
    """新建用户并发放 token。

    user_id 和 token 都是 uuid4，但刻意分开：token 是凭证，user_id 是标识。
    长期记忆会把 user_id 写进向量库的 payload，凭证不该出现在那里。
    """
    init_db()
    user_id = uuid.uuid4().hex
    token = uuid.uuid4().hex
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO users (user_id, token, name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, token, name, now),
        )
    return {"user_id": user_id, "token": token, "name": name, "created_at": now}


def get_user_by_token(token: str) -> dict | None:
    """按 token 查用户（认证入口）。token 无效返回 None。"""
    if not token:
        return None
    init_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT user_id, name, created_at FROM users WHERE token = ?", (token,)
        ).fetchone()
    return dict(row) if row else None


def revoke_token(token: str) -> bool:
    """吊销 token。"""
    init_db()
    with _db() as conn:
        cur = conn.execute("DELETE FROM users WHERE token = ?", (token,))
    return cur.rowcount > 0


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
