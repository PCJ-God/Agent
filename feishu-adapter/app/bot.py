"""事件处理：绑定命令 + 提问 → 网关 SSE → 卡片流式。"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from app.card import error_card, not_bound_card, render, thinking_card
from app.feishu_api import FeishuClient
from app.gateway import GatewayClient

logger = logging.getLogger("feishu.bot")

BIND_COMMANDS = {"绑定", "绑定账号", "绑定飞书"}
MIN_PATCH_INTERVAL = 0.3  # 卡片流式节流：最小补丁间隔（秒）


class Bot:
    def __init__(self) -> None:
        self.feishu = FeishuClient()
        self.gateway = GatewayClient()

    async def start(self) -> None:
        await self.feishu.load_bot_open_id()

    # ── 同步事件回调（WS 事件循环内调用） ──

    def on_message(self, data: P2ImMessageReceiveV1) -> None:
        """提取消息后，把异步处理挂到事件循环，避免阻塞长连接。"""
        try:
            ev = data.event
            sender = ev.sender
            msg = ev.message
            sender_type = getattr(sender, "sender_type", "user")
            msg_type = getattr(msg, "message_type", "?")
            chat_type = getattr(msg, "chat_type", "?")
            chat_id = getattr(msg, "chat_id", "")
            open_id = getattr(getattr(sender, "sender_id", None), "open_id", "") or ""
            logger.info(
                "收到飞书事件: chat_type=%s msg_type=%s sender_type=%s open_id=%s chat_id=%s",
                chat_type, msg_type, sender_type, open_id, chat_id,
            )

            if sender_type != "user":
                logger.info("跳过: 非用户消息 sender_type=%s", sender_type)
                return
            if msg_type != "text":
                logger.info("跳过: 非文本消息 msg_type=%s", msg_type)
                return
            if not open_id:
                logger.info("跳过: 缺少 open_id")
                return
            if chat_type == "group" and not self._is_mentioned(msg):
                logger.info("跳过: 群聊未 @机器人")
                return

            text = json.loads(msg.content or "{}").get("text", "").strip()
            if not text:
                logger.info("跳过: 文本为空")
                return

            logger.info("处理消息: open_id=%s text=%r", open_id, text)
            asyncio.get_event_loop().create_task(self._dispatch(chat_id, open_id, text))
        except Exception as exc:
            logger.exception("on_message 处理失败: %s", exc)

    def _is_mentioned(self, msg) -> bool:
        mentions = getattr(msg, "mentions", None) or []
        if not mentions:
            return False
        if not self.feishu.bot_open_id:
            return True  # 拿不到 bot open_id 时，退化为「只要 @ 人就响应」
        for m in mentions:
            mid = getattr(m, "id", None)
            if mid and getattr(mid, "open_id", "") == self.feishu.bot_open_id:
                return True
        return False

    # ── 异步处理 ──

    async def _dispatch(self, chat_id: str, open_id: str, text: str) -> None:
        try:
            if text in BIND_COMMANDS:
                await self._handle_bind(chat_id, open_id)
            else:
                await self._handle_chat(chat_id, open_id, text)
        except Exception as exc:
            logger.exception("dispatch 失败: %s", exc)
            try:
                await self.feishu.create_text(chat_id, f"出错了：{exc}")
            except Exception:
                pass

    async def _handle_bind(self, chat_id: str, open_id: str) -> None:
        code = await self.gateway.create_bind_code(open_id)
        text = (
            "绑定步骤：\n"
            "1. 在 Web 端登录你的账号\n"
            "2. 打开「飞书绑定」页\n"
            f"3. 输入验证码：{code}（5 分钟内有效）"
        )
        await self.feishu.create_text(chat_id, text)

    async def _handle_chat(self, chat_id: str, open_id: str, text: str) -> None:
        token = await self.gateway.resolve_token(open_id)
        if not token:
            await self.feishu.create_card(chat_id, not_bound_card())
            return

        msg_id = await self.feishu.create_card(chat_id, thinking_card())
        steps: list[str] = []
        answer = ""
        last_patch = 0.0
        done = False

        try:
            async for ev in self.gateway.chat(token, text, chat_id):
                t = ev.get("type")
                if t == "step":
                    s = ev.get("text", "")
                    if s and (not steps or steps[-1] != s):
                        steps.append(s)
                elif t == "delta":
                    answer += ev.get("text", "")
                elif t == "sources":
                    pass  # 引用来源暂不在卡片单独展示，正文已含 [编号]
                elif t == "error":
                    await self.feishu.patch_card(msg_id, error_card(ev.get("text", "")))
                    return
                elif t == "done":
                    done = True

                now = time.monotonic()
                if t in ("step", "done", "error") or (now - last_patch >= MIN_PATCH_INTERVAL):
                    await self.feishu.patch_card(msg_id, render(steps, answer))
                    last_patch = now

            if not done:
                await self.feishu.patch_card(msg_id, render(steps, answer or "（无回复）"))
        except Exception as exc:
            logger.exception("chat 流式失败: %s", exc)
            try:
                await self.feishu.patch_card(msg_id, error_card(str(exc)))
            except Exception:
                pass
