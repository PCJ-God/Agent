"""
Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    """问答请求。"""
    question: str = Field(description="用户问题")
    mode: str = Field(default="react", description="Agent 模式: react / hierarchical / cocreation")


class ChatResponse(BaseModel):
    """问答响应。"""
    answer: str = Field(description="Agent 回复")
    mode: str = Field(description="使用的 Agent 模式")


class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str = Field(default="ok")
    model: str = Field(description="当前使用的模型")
