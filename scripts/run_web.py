"""
Gradio Web UI — 流式输出，即时显示用户消息，统一后端文本提取
"""
import os
import asyncio
import gradio as gr
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import check_api_key, DASHSCOPE_API_KEY, MCP_SERVER_URL
from src.tools.tool_manager import register_mcp_tools, register_skill_tools, close_mcp_client
from src.agent_engine.react_agent import create_react_agent
from src.planning.plan_notebook import run_planning_workflow
from src.planning.reflection import external_feedback_mode
from src.planning.workflow import run_parallel_workflow, run_moa_workflow
from src.orchestration.hierarchical import HierarchicalTeam
from src.orchestration.cocreation import CoCreationTeam
from agentscope.tool import Toolkit
from agentscope.message import Msg
from agentscope.mcp import StdIOStatefulClient, HttpStatelessClient


# ── 文本提取 ──
def extract_text(response):
    if response is None:
        return ""
    content = response.content if hasattr(response, 'content') else response
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                texts.append(item.get("text", ""))
            elif hasattr(item, "text"):
                texts.append(item.text)
            elif isinstance(item, str):
                texts.append(item)
            else:
                texts.append(str(item))
        return "\n".join(texts)
    return str(content)


# ── 全局状态 ──
_shared_toolkit = None
_shared_mcp_client = None
_mcp_mode = "initializing"
_hierarchical_team = None
_cocreation_team = None


async def get_shared_toolkit():
    global _shared_toolkit, _shared_mcp_client, _mcp_mode
    if _shared_toolkit is None:
        _shared_toolkit = Toolkit()
        try:
            client = HttpStatelessClient(
                name="web_search_service",
                transport="streamable_http",
                url=MCP_SERVER_URL,
                headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
            )
            await _shared_toolkit.register_mcp_client(client)
            _shared_mcp_client = client
            _mcp_mode = "http (远程)"
        except Exception:
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
                _mcp_mode = "stdio (本地)"
            except Exception:
                _mcp_mode = "不可用"
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


# ── 工作流执行 (返回纯文本) ──
async def exec_react(message, toolkit):
    agent = create_react_agent(toolkit=toolkit)
    response = await agent(Msg("user", message, "user"))
    return extract_text(response)


async def exec_planning(message, toolkit):
    result = await run_planning_workflow(message, toolkit=toolkit, mcp_client=_shared_mcp_client)
    return str(result) if isinstance(result, dict) else str(result)


async def exec_parallel(message, toolkit):
    return await run_parallel_workflow(message)


async def exec_moa(message):
    return await run_moa_workflow(message)


async def exec_hierarchical(message):
    team = get_hierarchical_team()
    return await team.chat(message)


async def exec_cocreation(message):
    team = get_cocreation_team()
    return await team.discuss(message)


async def exec_external_feedback(message):
    return await external_feedback_mode(message)


WORKFLOW_FN = {
    "ReAct Agent": exec_react,
    "Planning Notebook": exec_planning,
    "Parallel Review": exec_parallel,
    "MoA": exec_moa,
    "Hierarchical": exec_hierarchical,
    "Co-creation": exec_cocreation,
    "External Feedback": exec_external_feedback,
}


# ── Gradio 界面 ──
def init_ui():
    check_api_key()
    loop = asyncio.new_event_loop()
    loop.run_until_complete(get_shared_toolkit())
    loop.close()

    with gr.Blocks(title="Agent 智能教学助手") as demo:
        gr.Markdown("# Agent 智能教学助手")
        gr.Markdown("选择工作流，流式对话。MCP 优先远程，回退本地。")

        with gr.Row():
            with gr.Column(scale=1):
                workflow = gr.Dropdown(
                    choices=list(WORKFLOW_FN.keys()),
                    value="ReAct Agent",
                    label="选择工作流",
                )
                mcp_status = gr.Textbox(label="MCP 状态", value=_mcp_mode, interactive=False)

            with gr.Column(scale=2):
                chatbot = gr.Chatbot(label="对话", height=500)
                with gr.Row():
                    msg = gr.Textbox(label="输入问题", placeholder="输入你的问题...", scale=4)
                    send_btn = gr.Button("发送", scale=1)
                clear_btn = gr.Button("清空")

        async def respond(message, history, wf):
            if not message:
                yield history, ""
                return

            # 1. 立即显示用户消息
            history = history + [[message, None]]
            yield history, ""

            # 2. 执行工作流
            run_fn = WORKFLOW_FN.get(wf)
            toolkit = _shared_toolkit
            try:
                if wf == "MoA":
                    result = await exec_moa(message)
                elif wf == "Hierarchical":
                    result = await exec_hierarchical(message)
                elif wf == "Co-creation":
                    result = await exec_cocreation(message)
                elif wf == "External Feedback":
                    result = await exec_external_feedback(message)
                else:
                    result = await run_fn(message, toolkit)
            except Exception as e:
                result = f"❌ 错误: {e}"

            # 3. 更新 Agent 回复
            history[-1][1] = result
            yield history, ""

        workflow.change(lambda: _mcp_mode, outputs=[mcp_status])
        msg.submit(respond, inputs=[msg, chatbot, workflow], outputs=[chatbot, msg])
        send_btn.click(respond, inputs=[msg, chatbot, workflow], outputs=[chatbot, msg])
        clear_btn.click(lambda: ([], ""), outputs=[chatbot, msg])

    demo.launch(server_name="127.0.0.1", server_port=7860)


if __name__ == "__main__":
    init_ui()
