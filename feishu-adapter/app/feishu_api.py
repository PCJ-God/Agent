"""飞书 API：普通消息发送、CardKit 流式卡片、图片下载。

- 普通消息（思考中/错误/未绑定提示）走 im/v1/messages
- 聊天回复走 CardKit 流式卡片（cardkit/v1）：组件级增量更新，客户端 typewriter，更顺滑
- 图片下载走 im/v1/messages/{id}/resources/{key}?type=image
"""
from __future__ import annotations

import json
import time
import uuid

import httpx

from app.config import FEISHU_APP_ID, FEISHU_APP_SECRET

FEISHU_BASE = "https://open.feishu.cn/open-apis"


class FeishuClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._bot_open_id: str | None = None

    @property
    def bot_open_id(self) -> str | None:
        return self._bot_open_id

    async def _tenant_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_exp - 60:
            return self._token
        resp = await self._http.post(
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        )
        data = resp.json()
        self._token = data.get("tenant_access_token", "")
        self._token_exp = now + int(data.get("expire", 7200))
        return self._token

    async def _headers(self) -> dict:
        return {"Authorization": f"Bearer {await self._tenant_token()}"}

    async def load_bot_open_id(self) -> None:
        try:
            resp = await self._http.get(f"{FEISHU_BASE}/bot/v3/info", headers=await self._headers())
            data = resp.json().get("data", {})
            self._bot_open_id = (data.get("bot") or {}).get("open_id") or None
        except Exception:
            self._bot_open_id = None

    # ── 普通消息 ──

    async def _send_message(self, chat_id: str, msg_type: str, content: str) -> str:
        resp = await self._http.post(
            f"{FEISHU_BASE}/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={**await self._headers(), "Content-Type": "application/json"},
            json={"receive_id": chat_id, "msg_type": msg_type, "content": content},
        )
        data = resp.json()
        if data.get("code", 0) != 0:
            raise RuntimeError(f"发送消息失败: {data}")
        return (data.get("data") or {}).get("message_id", "")

    async def create_text(self, chat_id: str, text: str) -> None:
        await self._send_message(chat_id, "text", json.dumps({"text": text}, ensure_ascii=False))

    async def create_card(self, chat_id: str, card_json: str) -> str:
        return await self._send_message(chat_id, "interactive", card_json)

    async def patch_card(self, message_id: str, card_json: str) -> None:
        """兜底路径（CardKit 不可用时）：整卡替换。"""
        resp = await self._http.patch(
            f"{FEISHU_BASE}/im/v1/messages/{message_id}",
            headers={**await self._headers(), "Content-Type": "application/json"},
            json={"content": card_json},
        )
        data = resp.json()
        if data.get("code", 0) != 0:
            raise RuntimeError(f"更新卡片失败: {data}")

    # ── CardKit 流式卡片 ──

    async def create_card_entity(self, card_json: str) -> str:
        resp = await self._http.post(
            f"{FEISHU_BASE}/cardkit/v1/cards",
            headers={**await self._headers(), "Content-Type": "application/json"},
            json={"type": "card_json", "data": card_json},
        )
        data = resp.json()
        if data.get("code", 0) != 0:
            raise RuntimeError(f"创建卡片实体失败: {data}")
        return (data.get("data") or {}).get("card_id", "")

    async def send_card_entity(self, chat_id: str, card_id: str) -> str:
        content = json.dumps({"type": "card", "data": {"card_id": card_id}})
        return await self._send_message(chat_id, "interactive", content)

    async def stream_card_text(self, card_id: str, element_id: str, text: str, sequence: int) -> None:
        resp = await self._http.put(
            f"{FEISHU_BASE}/cardkit/v1/cards/{card_id}/elements/{element_id}/content",
            headers={**await self._headers(), "Content-Type": "application/json"},
            json={"content": text, "sequence": sequence, "uuid": str(uuid.uuid4())},
        )
        data = resp.json()
        if data.get("code", 0) != 0:
            raise RuntimeError(f"流式更新失败: {data}")

    async def close_card_stream(self, card_id: str, sequence: int) -> None:
        settings = json.dumps({"config": {"streaming_mode": False}})
        resp = await self._http.patch(
            f"{FEISHU_BASE}/cardkit/v1/cards/{card_id}/settings",
            headers={**await self._headers(), "Content-Type": "application/json"},
            json={"settings": settings, "sequence": sequence, "uuid": str(uuid.uuid4())},
        )
        data = resp.json()
        if data.get("code", 0) != 0:
            raise RuntimeError(f"关闭流式失败: {data}")

    # ── 图片下载 ──

    async def download_image(self, message_id: str, file_key: str) -> bytes | None:
        resp = await self._http.get(
            f"{FEISHU_BASE}/im/v1/messages/{message_id}/resources/{file_key}",
            params={"type": "image"},
            headers=await self._headers(),
        )
        ctype = resp.headers.get("content-type", "")
        if resp.status_code == 200 and ctype.startswith("image"):
            return resp.content
        return None

    async def close(self) -> None:
        await self._http.aclose()
