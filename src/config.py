"""
配置管理模块 — 全局配置
"""
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ==================== 路径配置 ====================
PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
#: 用户自建技能的物化目录（<- SQLite 里的 user_skills 表）。
#: 库是唯一事实来源，这里只是给 agentscope 用的视图 —— 它只认目录里的 SKILL.md。
USER_SKILLS_DIR = PROJECT_ROOT / "data" / "skills"


# ==================== API 配置 ====================
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")


# ==================== 模型配置 ====================
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "2048"))


# ==================== Agent 配置 ====================
MAX_REACT_ITERS = int(os.getenv("MAX_REACT_ITERS", "10"))


# ==================== Memory 配置 ====================
MAX_MEMORY_TOKENS = int(os.getenv("MAX_MEMORY_TOKENS", "4096"))

ENABLE_LONG_TERM_MEMORY = os.getenv("ENABLE_LONG_TERM_MEMORY", "false").lower() == "true"
QDRANT_PATH = os.getenv("QDRANT_PATH", str(PROJECT_ROOT / "data" / "memory" / "qdrant"))
# 公网部署必须用 server 模式：本地文件版是单进程独占的，多个 worker 会互相抢锁。
# 设了 QDRANT_URL 就走 server，否则退回本地文件（仅适合开发）。
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

# 长期记忆作用域（映射到 Mem0 的 run_id）:
#   session —— 每个会话一个独立记忆域，并行任务之间互不干扰
#   global  —— 所有会话共用一个记忆域，跨会话累积
LTM_SCOPE = os.getenv("LTM_SCOPE", "session").lower()


# ==================== 会话（任务）配置 ====================
# 会话历史库（SQLite）：一个会话 = 一个任务，历史按会话持久化、可分页读取
SESSIONS_DB = PROJECT_ROOT / "data" / "sessions.db"
# 重新打开任务时，回放最近多少轮对话进 Leader 的记忆（每轮 = 提问 + 回复）
HISTORY_REPLAY_TURNS = int(os.getenv("HISTORY_REPLAY_TURNS", "10"))

# ==================== 公网部署：资源隔离 ====================
# 每个用户最多建多少个任务
MAX_SESSIONS_PER_USER = int(os.getenv("MAX_SESSIONS_PER_USER", "50"))
# 进程内最多同时保留多少个任务的内存实例（超出按 LRU 淘汰空闲的；历史仍在 SQLite）
MAX_TEAMS = int(os.getenv("MAX_TEAMS", "20"))
# 每个用户每分钟最多几次对话请求（<=0 表示不限流）
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))

# ==================== 监听与 HTTPS ====================
# 监听地址。挂了反向代理就保持 127.0.0.1（只有本机能连，由代理对外）；
# 没有代理才需要 0.0.0.0。
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
# 直连 HTTPS 时填证书路径；挂了反向代理就留空（证书交给代理，应用只跑 HTTP）
SSL_CERTFILE = os.getenv("SSL_CERTFILE", "")
SSL_KEYFILE = os.getenv("SSL_KEYFILE", "")
# 信任哪些来源发来的 X-Forwarded-* 头。默认只信本机 —— 反向代理跑在同机时
# 这已经够用；代理在别的机器上就填它的 IP。绝不要填 "*"。
FORWARDED_ALLOW_IPS = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")


# ==================== MCP 配置 ====================
# 只使用远程 MCP（DashScope 联网搜索），本地 stdio 模拟服务已移除
MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL",
    "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp",
)


def check_api_key():
    """检查 API Key 是否配置。"""
    if not DASHSCOPE_API_KEY or DASHSCOPE_API_KEY.startswith("sk-your"):
        raise ValueError(
            "请先在 .env 文件中配置 DASHSCOPE_API_KEY\n"
            "获取地址: https://bailian.console.aliyun.com/?apiKey=1"
        )
    return True


# ==================== 日志配置 ====================
def setup_logging(level: int = logging.INFO) -> None:
    """配置应用日志（入口处调用一次）。

    项目里原本没有任何 logging 配置，导致只有 agentscope 自带 handler 的日志
    可见 —— 它在 agentscope/_logging.py:44 显式设了 `propagate = False` ——
    而本项目模块的 logger.info 会被 root 默认的 WARNING 级别静默丢弃。

    因为 agentscope 不向上传播，这里配置 root 不会造成它的日志重复输出。

    Args:
        level: 日志级别，默认 INFO
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    # 这两个库会给每个 HTTP 请求打一条 INFO，噪音远大于价值
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
