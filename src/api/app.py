"""
FastAPI Web 服务
提供 REST API 端点
"""
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from src.config import LLM_MODEL, check_api_key
from src.api.schemas import ChatRequest, ChatResponse, HealthResponse
from src.agent_engine.react_agent import run_agent_query
from src.tools.tool_manager import register_default_tools
from src.orchestration.hierarchical import run_hierarchical
from src.orchestration.cocreation import run_cocreation
from agentscope.tool import Toolkit


app = FastAPI(title="Agent 智能教学助手", version="1.0.0")


@app.on_event("startup")
async def startup():
    """启动时检查 API Key。"""
    try:
        check_api_key()
    except ValueError as e:
        raise RuntimeError(str(e))

@app.get("/")
async def root():
    """根路径，返回服务信息。"""
    return {"message": "Agent 智能教学助手 API", "version": "1.0.0"}

@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查。"""
    return HealthResponse(status="ok", model=LLM_MODEL)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """单轮问答。

    支持三种 Agent 模式:
    - react: ReAct 单 Agent
    - hierarchical: 层级协作
    - cocreation: 圆桌共创
    """
    try:
        if request.mode == "react":
            toolkit = Toolkit()
            register_default_tools(toolkit)
            answer = await run_agent_query(request.question, toolkit=toolkit)

        elif request.mode == "hierarchical":
            answer = await run_hierarchical(request.question)

        elif request.mode == "cocreation":
            answer = await run_cocreation(request.question)

        else:
            raise HTTPException(status_code=400, detail=f"不支持的模式: {request.mode}")

        return ChatResponse(answer=answer, mode=request.mode)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式问答 (SSE)。"""
    async def event_generator():
        toolkit = Toolkit()
        register_default_tools(toolkit)

        try:
            from agentscope.message import Msg
            from src.agent_engine.react_agent import create_react_agent

            agent = create_react_agent(toolkit=toolkit)
            msg = Msg(name="user", content=request.question, role="user")
            response = await agent(msg)

            yield f"data: {response.content}\n\n"

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
