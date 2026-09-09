"""
Agent Web Backend — FastAPI + 工作流执行
提供 REST API 供前端调用
"""
import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.config import check_api_key, DASHSCOPE_API_KEY, MCP_SERVER_URL
from src.tools.tool_manager import register_mcp_tools, register_skill_tools, close_mcp_client
from src.agent_engine.react_agent import create_react_agent
from src.planning.plan_notebook import run_planning_workflow
from src.planning.reflection import external_feedback_mode
from src.planning.workflow import run_parallel_workflow, run_moa_workflow
from src.orchestration.hierarchical import HierarchicalTeam
from src.orchestration.cocreation import CoCreationTeam
from src.api.schemas import ChatRequest, AgentResponse, HealthResponse
from agentscope.tool import Toolkit
from agentscope.message import Msg
from agentscope.mcp import StdIOStatefulClient, HttpStatelessClient

app = FastAPI(title="Agent API")

# ── 全局状态 ──
_shared_toolkit = None
_shared_mcp_client = None
_hierarchical_team = None
_cocreation_team = None
_mcp_status = "initializing"


def extract_text(response):
    if response is None:
        return ""
    content = response.content if hasattr(response, 'content') else response
    if content is None:
        return ""
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text", "")
                if t:
                    texts.append(t)
            elif isinstance(item, str):
                texts.append(item)
            else:
                t = str(item)
                if t:
                    texts.append(t)
        return "\n".join(texts) if texts else ""
    return str(content) if content else ""


async def get_shared_toolkit():
    global _shared_toolkit, _shared_mcp_client, _mcp_status
    if _shared_toolkit is None:
        _shared_toolkit = Toolkit()
        # 优先远程 MCP (HttpStatelessClient 不需要 connect)
        try:
            client = HttpStatelessClient(
                name="web_search_service",
                transport="streamable_http",
                url=MCP_SERVER_URL,
                headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
            )
            await _shared_toolkit.register_mcp_client(client)
            _shared_mcp_client = client
            _mcp_status = "http (远程)"
        except Exception as e:
            # 回退本地 MCP
            try:
                from src.config import MCP_SERVERS_DIR
                server_script = MCP_SERVERS_DIR / "web_search_server.py"
                client = StdIOStatefulClient(
                    name="web_search_service",
                    command=sys.executable,
                    args=[str(server_script)],
                    cwd=os.getcwd(),
                )
                await client.connect()
                await _shared_toolkit.register_mcp_client(client)
                _shared_mcp_client = client
                _mcp_status = "stdio (本地)"
            except Exception:
                _mcp_status = "不可用"
        register_skill_tools(_shared_toolkit)
    return _shared_toolkit


def get_hierarchical_team():
    global _hierarchical_team
    if _hierarchical_team is None:
        _hierarchical_team = HierarchicalTeam()
    return _hierarchical_team


def get_cocreation_team():
    global _cocreation_team
    if _cocreation_team is None:
        _cocreation_team = CoCreationTeam()
    return _cocreation_team


# ── 工作流执行 ──
async def exec_workflow(req: ChatRequest) -> str:
    toolkit = await get_shared_toolkit()
    wf = req.workflow

    if wf == "react":
        agent = create_react_agent(toolkit=toolkit)
        response = await agent(Msg("user", req.message, "user"))
        return extract_text(response)
    elif wf == "planning":
        return await run_planning_workflow(req.message, toolkit=toolkit, mcp_client=_shared_mcp_client)
    elif wf == "parallel":
        return await run_parallel_workflow(req.message)
    elif wf == "moa":
        return await run_moa_workflow(req.message)
    elif wf == "hierarchical":
        team = get_hierarchical_team()
        return await team.chat(req.message)
    elif wf == "cocreation":
        team = get_cocreation_team()
        return await team.discuss(req.message)
    elif wf == "feedback":
        return await external_feedback_mode(req.message)
    else:
        raise ValueError(f"未知工作流: {wf}")


# ── API 路由 ──
@app.on_event("startup")
async def startup():
    check_api_key()
    await get_shared_toolkit()


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", mcp=_mcp_status)


@app.post("/api/chat", response_model=AgentResponse)
async def chat(req: ChatRequest):
    print(f"收到请求: workflow={req.workflow}, message={req.message[:50]}...")
    if not req.message:
        return AgentResponse(workflow=req.workflow, success=False, response="", error="消息不能为空")
    try:
        result = await exec_workflow(req)
        print(f"返回结果: success=True, length={len(result)}")
        return AgentResponse(
            workflow=req.workflow,
            success=True,
            response=result,
        )
    except Exception as e:
        error_msg = f"工作流执行错误: {e}"
        print(f"返回结果: success=False, error={error_msg}")
        return AgentResponse(
            workflow=req.workflow,
            success=False,
            response="",
            error=error_msg,
        )


# ── 前端静态文件 ──
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
