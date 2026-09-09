"""
Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ChatRequest(BaseModel):
    """问答请求。"""
    message: str = Field(description="用户问题")
    workflow: str = Field(default="react", description="工作流: react/planning/parallel/hierarchical/cocreation/moa/feedback")


class AgentResponse(BaseModel):
    """统一的 Agent 响应类。"""
    workflow: str = Field(description="使用的工作流")
    success: bool = Field(description="是否成功执行")
    response: str = Field(description="Agent 回复内容")
    error: Optional[str] = Field(default=None, description="错误信息")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str = Field(default="ok")
    mcp: str = Field(default="disconnected", description="MCP 连接状态")
