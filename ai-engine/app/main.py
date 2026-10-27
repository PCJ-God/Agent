"""ACP Copilot — AI 引擎。

HTTP 仅保留 /health /metrics（Docker 探活 + Prometheus 采集），业务全走 gRPC（50051）。
"""
from contextlib import asynccontextmanager

import grpc
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app import grpc_server, metrics
from gen import assistant_pb2_grpc


@asynccontextmanager
async def lifespan(_: FastAPI):
    server = grpc.aio.server()
    assistant_pb2_grpc.add_AssistantServiceServicer_to_server(
        grpc_server.AssistantServicer(), server
    )
    server.add_insecure_port("[::]:50051")
    await server.start()
    yield
    await server.stop(0)


app = FastAPI(title="ACP Copilot AI Engine", lifespan=lifespan)


@app.middleware("http")
async def count_requests(request: Request, call_next):
    metrics.inc(request.url.path)
    return await call_next(request)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ai-engine"}


@app.get("/metrics")
async def get_metrics() -> PlainTextResponse:
    return PlainTextResponse(metrics.render())
