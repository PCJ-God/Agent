"""飞书 API：发卡片/文本、流式更新卡片、获取机器人 open_id。

全部用 lark-oapi 的异步方法（acreate/apatch），避免在长连接事件循环里做阻塞 HTTP。
"""
from __future__ import annotations

import json

import httpx
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    PatchMessageRequest,
    PatchMessageRequestBody,
)

from app.config import FEISHU_APP_ID, FEISHU_APP_SECRET


class FeishuClient:
    def __init__(self) -> None:
        self._lark = (
            lark.Client.builder()
            .app_id(FEISHU_APP_ID)
            .app_secret(FEISHU_APP_SECRET)
            .build()
        )
        self._bot_open_id: str | None = None

    @property
    def bot_open_id(self) -> str | None:
        return self._bot_open_id

    async def load_bot_open_id(self) -> None:
        """获取机器人自身 open_id（群聊 @ 过滤用），失败则置 None 退化为宽松策略。"""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                token_resp = await client.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
                )
                token = token_resp.json().get("tenant_access_token", "")
                info_resp = await client.get(
                    "https://open.feishu.cn/open-apis/bot/v3/info",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = info_resp.json().get("data", {})
                self._bot_open_id = data.get("bot", {}).get("open_id") or None
        except Exception:
            self._bot_open_id = None

    async def create_card(self, chat_id: str, card_json: str) -> str:
        """发送一张卡片消息，返回 message_id（后续 patch 用）。"""
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(card_json)
                .build()
            )
            .build()
        )
        resp = await self._lark.im.v1.message.acreate(req)
        if not resp.success():
            raise RuntimeError(f"发卡片失败: code={resp.code} msg={resp.msg}")
        return resp.data.message_id

    async def create_text(self, chat_id: str, text: str) -> None:
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        resp = await self._lark.im.v1.message.acreate(req)
        if not resp.success():
            raise RuntimeError(f"发文本失败: code={resp.code} msg={resp.msg}")

    async def patch_card(self, message_id: str, card_json: str) -> None:
        req = (
            PatchMessageRequest.builder()
            .message_id(message_id)
            .request_body(PatchMessageRequestBody.builder().content(card_json).build())
            .build()
        )
        resp = await self._lark.im.v1.message.apatch(req)
        if not resp.success():
            raise RuntimeError(f"更新卡片失败: code={resp.code} msg={resp.msg}")
