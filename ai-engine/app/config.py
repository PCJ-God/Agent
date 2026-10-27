"""AI 引擎配置：从环境变量读取（docker-compose 注入）。"""
import os

# DashScope 模型
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
DASHSCOPE_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
EMBEDDING_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")

# RAG：向量库（Qdrant）+ 重排
RAG_COLLECTION = os.getenv("RAG_COLLECTION", "acp_docs")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
RERANK_MODEL = os.getenv("RERANK_MODEL", "gte-rerank")
DOCS_DIR = os.getenv("DOCS_DIR", "/app/data/docs")

# 记忆：mem0 长期记忆（agent_control 模式）
MEMORY_EMBED_DIM = int(os.getenv("MEMORY_EMBED_DIM", "2048"))
MEMORY_COLLECTION = os.getenv("MEMORY_COLLECTION", "mem0")

# Agent
MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL", "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp"
)
MAX_AGENT_ITERS = int(os.getenv("MAX_AGENT_ITERS", "8"))

# Redis：文档解析结果缓存（worker 写、ai-engine 读）
REDIS_ADDR = os.getenv("REDIS_ADDR", "redis:6379")
PARSE_RESULT_TTL = int(os.getenv("PARSE_RESULT_TTL", "1800"))

# 上传限制
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
MAX_FILES = int(os.getenv("MAX_FILES", "5"))
MAX_TOTAL_MB = int(os.getenv("MAX_TOTAL_MB", "30"))
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "30000"))

# OCR：照片 / 扫描件（DashScope 视觉 OCR）
OCR_MODEL = os.getenv("OCR_MODEL", "qwen-vl-ocr")

# 异步：文档解析队列
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://acp:acp@rabbitmq:5672/")
