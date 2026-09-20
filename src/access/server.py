"""
接入层 - FastAPI Server
提供 REST API 和原生 HTML 前端

四层架构:
  接入层 (本模块) → 调度层 (HierarchicalTeam) → 执行层 (Agents + MCP + Skills) → 存储层 (Memory)
"""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from src.config import check_api_key, setup_logging
from src.orchestration.hierarchical import HierarchicalTeam


# ── 数据模型 ──
class ChatRequest(BaseModel):
    message: str = Field(description="用户问题")


class AgentResponse(BaseModel):
    success: bool = Field(description="是否成功执行")
    response: str = Field(description="Agent 回复内容")
    error: Optional[str] = Field(default=None, description="错误信息")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class HealthResponse(BaseModel):
    status: str = "ok"
    mcp: str = "disconnected"


# ── FastAPI 应用 ──
_hierarchical_team: HierarchicalTeam | None = None


async def get_team() -> HierarchicalTeam:
    """获取（惰性装配的）团队单例。

    整个进程共用一个，因此三个 Agent 的短期记忆、长期记忆池、MCP 连接
    都是跨请求保留的。
    """
    global _hierarchical_team
    if _hierarchical_team is None:
        _hierarchical_team = await HierarchicalTeam.create()
    return _hierarchical_team


def mcp_status() -> str:
    """MCP 连接状态（供 /health 展示）。"""
    if _hierarchical_team is None:
        return "initializing"
    return "connected" if _hierarchical_team.mcp_client is not None else "unavailable"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时一次性完成装配：MCP 客户端 + 向量库 + 三个 Agent。"""
    check_api_key()
    await get_team()
    yield


app = FastAPI(title="Agent API — Hierarchical Mode", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", mcp=mcp_status())


@app.post("/api/chat", response_model=AgentResponse)
async def chat(req: ChatRequest):
    if not req.message:
        return AgentResponse(success=False, response="", error="消息不能为空")

    try:
        team = await get_team()
        result = await team.chat(req.message)
        return AgentResponse(success=True, response=result)
    except Exception as e:
        return AgentResponse(success=False, response="", error=str(e))


# ── 流式对话 (SSE) ──
_chat_lock = asyncio.Lock()
_STREAM_DONE = object()


def _sse(payload: dict) -> str:
    """把一条数据编码成 SSE 帧。"""
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式对话: 把三个 Agent 的输出实时推给前端 (Server-Sent Events)。

    与 /api/chat 的区别: 后者要等整轮协作结束后一次性返回，
    本端点在整个执行过程中持续推送增量文本。
    """
    if not req.message:
        raise HTTPException(status_code=400, detail="消息不能为空")
    if _chat_lock.locked():
        raise HTTPException(status_code=409, detail="已有对话正在进行，请稍后再试")

    team = await get_team()
    queue: asyncio.Queue = asyncio.Queue()   # 不设上限，避免 Agent 阻塞在 put()
    team.enable_streaming(queue)
    await _chat_lock.acquire()

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
            _chat_lock.release()

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


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


def run():
    import uvicorn

    setup_logging()
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()