"""AI 引擎配置：从环境变量读取（由 docker-compose 注入）。"""
import os

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")

# DashScope 的 OpenAI 兼容接口（与现有项目 model.py 一致）
DASHSCOPE_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# RAG：向量化与向量库
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
CHROMA_HOST = os.getenv("CHROMA_HOST", "chroma")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_URL = os.getenv("CHROMA_URL", f"http://{CHROMA_HOST}:{CHROMA_PORT}")
DOCS_DIR = os.getenv("DOCS_DIR", "/app/data/docs")

# Agent：联网搜索（DashScope MCP，无状态 streamable HTTP）
MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL", "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp"
)
MAX_AGENT_ITERS = int(os.getenv("MAX_AGENT_ITERS", "5"))

# 记忆：短期（Redis 滑动窗口）+ 长期（Qdrant 用户画像）
REDIS_ADDR = os.getenv("REDIS_ADDR", "redis:6379")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
MEMORY_WINDOW = int(os.getenv("MEMORY_WINDOW", "20"))
MEMORY_SUMMARY_KEEP = int(os.getenv("MEMORY_SUMMARY_KEEP", "6"))

# 异步：文档解析队列
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://acp:acp@rabbitmq:5672/")
