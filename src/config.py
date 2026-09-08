# 配置管理模块
# 集中管理 API Key、模型参数、Agent 配置等
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# ==================== 路径配置 ====================
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SKILLS_DIR = PROJECT_ROOT / "skills"
MCP_SERVERS_DIR = PROJECT_ROOT / "mcp_servers"


# ==================== API 配置 ====================
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


# ==================== 模型配置 ====================
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "2048"))


# ==================== Agent 配置 ====================
MAX_REACT_ITERS = int(os.getenv("MAX_REACT_ITERS", "10"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.0"))


# ==================== Memory 配置 ====================
MEMORY_STRATEGY = os.getenv("MEMORY_STRATEGY", "InMemoryMemory")  # InMemoryMemory / ContextTruncation
MAX_MEMORY_TOKENS = int(os.getenv("MAX_MEMORY_TOKENS", "4096"))

# 长期记忆 (Mem0 + Qdrant)
ENABLE_LONG_TERM_MEMORY = os.getenv("ENABLE_LONG_TERM_MEMORY", "false").lower() == "true"
QDRANT_PATH = os.getenv("QDRANT_PATH", str(PROJECT_ROOT / "data" / "memory" / "qdrant"))


# ==================== MCP 配置 ====================
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")  # stdio / streamable_http
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp")


def check_api_key():
    """检查 API Key 是否配置"""
    if not DASHSCOPE_API_KEY or DASHSCOPE_API_KEY.startswith("sk-your"):
        raise ValueError(
            "请先在 .env 文件中配置 DASHSCOPE_API_KEY\n"
            "获取地址: https://bailian.console.aliyun.com/?apiKey=1"
        )
    return True
