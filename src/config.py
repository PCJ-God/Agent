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
