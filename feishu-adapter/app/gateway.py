"""网关客户端：内部端点（绑定码 / open_id→JWT）+ /api/assistant SSE。"""
from __future__ import annotations

import json
from typing import AsyncGenerator

import httpx

from app.config import GATEWAY_URL, INTERNAL_TOKEN


class GatewayError(Exception):
    pass


class GatewayClient:
    def __init__(self) -> None:
        # read=None：SSE 长连接不设读取超时；其余 30s
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None))

    def _headers(self) -> dict:
        return {"X-Internal-Token": INTERNAL_TOKEN}

    async def create_bind_code(self, open_id: str) -> str:
        resp = await self._client.post(
            f"{GATEWAY_URL}/api/internal/feishu/bind-code",
            headers=self._headers(),
            json={"open_id": open_id},
        )
        if resp.status_code != 200:
            raise GatewayError(f"bind-code 失败: HTTP {resp.status_code}")
        return resp.json().get("code", "")

    async def resolve_token(self, open_id: str) -> str | None:
        """按 open_id 换取绑定用户的 JWT；未绑定返回 None。"""
        resp = await self._client.post(
            f"{GATEWAY_URL}/api/internal/feishu/token",
            headers=self._headers(),
            json={"open_id": open_id},
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise GatewayError(f"resolve token 失败: HTTP {resp.status_code}")
        return resp.json().get("token")

    async def chat(self, token: str, message: str, session_id: str) -> AsyncGenerator[dict, None]:
        """调 /api/assistant，逐事件 yield（step / delta / sources / done / error）。"""
        async with self._client.stream(
            "POST",
            f"{GATEWAY_URL}/api/assistant",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"message": message, "session_id": session_id, "task_ids": []},
        ) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", "ignore")
                yield {"type": "error", "text": f"HTTP {resp.status_code}: {body[:200]}"}
                return
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue

    async def close(self) -> None:
        await self._client.aclose()
