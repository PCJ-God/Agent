"""事件处理：绑定命令 + 提问/图片 → 网关 SSE → CardKit 流式卡片。"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from app.card import (
    ELEMENT_ID,
    build_stream_text,
    error_card,
    not_bound_card,
    render,
    streaming_card,
    thinking_card,
)
from app.feishu_api import FeishuClient
from app.gateway import GatewayClient

logger = logging.getLogger("feishu.bot")

BIND_COMMANDS = {"绑定", "绑定账号", "绑定飞书"}
FLUSH_INTERVAL = 0.25   # 流式刷新节流（秒）：本地聚合最新文本，后台按节奏推
MIN_PATCH_INTERVAL = 0.3  # 回退整卡 patch 的节流
SUPPORTED_MSG = ("text", "image", "post")


class Bot:
    def __init__(self) -> None:
        self.feishu = FeishuClient()
        self.gateway = GatewayClient()

    async def start(self) -> None:
        await self.feishu.load_bot_open_id()

    # ── 同步事件回调（WS 事件循环内调用） ──

    def on_message(self, data: P2ImMessageReceiveV1) -> None:
        try:
            ev = data.event
            sender = ev.sender
            msg = ev.message
            sender_type = getattr(sender, "sender_type", "user")
            msg_type = getattr(msg, "message_type", "?")
            chat_type = getattr(msg, "chat_type", "?")
            chat_id = getattr(msg, "chat_id", "")
            message_id = getattr(msg, "message_id", "")
            open_id = getattr(getattr(sender, "sender_id", None), "open_id", "") or ""
            logger.info(
                "收到飞书事件: chat_type=%s msg_type=%s sender_type=%s open_id=%s",
                chat_type, msg_type, sender_type, open_id,
            )

            if sender_type != "user":
                return
            if msg_type not in SUPPORTED_MSG:
                logger.info("跳过: 不支持的消息类型 msg_type=%s", msg_type)
                return
            if not open_id:
                logger.info("跳过: 缺少 open_id")
                return
            if chat_type == "group" and not self._is_mentioned(msg):
                logger.info("跳过: 群聊未 @机器人")
                return

            text, image_keys = self._extract(msg_type, getattr(msg, "content", "") or "")
            if not text and not image_keys:
                logger.info("跳过: 无文本且无图片")
                return

            logger.info("处理消息: msg_type=%s text=%r images=%d", msg_type, text, len(image_keys))
            asyncio.get_event_loop().create_task(
                self._dispatch(chat_id, open_id, text, image_keys, message_id)
            )
        except Exception as exc:
            logger.exception("on_message 处理失败: %s", exc)

    def _extract(self, msg_type: str, content: str) -> tuple[str, list[str]]:
        try:
            obj = json.loads(content or "{}")
        except Exception:
            return "", []
        if msg_type == "text":
            return (obj.get("text", "") or "").strip(), []
        if msg_type == "image":
            ik = obj.get("image_key", "")
            return "", ([ik] if ik else [])
        if msg_type == "post":
            texts: list[str] = []
            imgs: list[str] = []
            title = obj.get("title", "")
            if title:
                texts.append(title)
            for para in obj.get("content", []) or []:
                if not isinstance(para, list):
                    continue
                for el in para:
                    if not isinstance(el, dict):
                        continue
                    if el.get("tag") == "text" and el.get("text"):
                        texts.append(el["text"])
                    elif el.get("tag") == "img" and el.get("image_key"):
                        imgs.append(el["image_key"])
            return " ".join(t for t in texts if t).strip(), imgs
        return "", []

    def _is_mentioned(self, msg) -> bool:
        mentions = getattr(msg, "mentions", None) or []
        if not mentions:
            return False
        if not self.feishu.bot_open_id:
            return True
        for m in mentions:
            mid = getattr(m, "id", None)
            if mid and getattr(mid, "open_id", "") == self.feishu.bot_open_id:
                return True
        return False

    # ── 异步处理 ──

    async def _dispatch(self, chat_id, open_id, text, image_keys, message_id) -> None:
        try:
            if not image_keys and text in BIND_COMMANDS:
                await self._handle_bind(chat_id, open_id)
            else:
                await self._handle_chat(chat_id, open_id, text, image_keys, message_id)
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

    async def _handle_chat(self, chat_id, open_id, text, image_keys, message_id) -> None:
        token = await self.gateway.resolve_token(open_id)
        if not token:
            await self.feishu.create_card(chat_id, not_bound_card())
            return
        try:
            await self._run_streaming(chat_id, token, text, image_keys, message_id)
        except Exception as exc:
            logger.warning("CardKit 流式失败，回退整卡 patch：%s", exc)
            await self._run_patch(chat_id, token, text, image_keys, message_id)

    async def _prepare_attachments(self, token, image_keys, message_id):
        """下载图片 → 上传网关 → 等待解析，返回 task_ids。"""
        if not image_keys:
            return []
        data = await self.feishu.download_image(message_id, image_keys[0])
        if not data:
            return []
        task_ids = await self.gateway.upload_file(token, "feishu_image.jpg", data, "image/jpeg")
        if not task_ids:
            return []
        await self._wait_parse(token, task_ids)
        return task_ids

    async def _wait_parse(self, token, task_ids: list[str]) -> None:
        for _ in range(40):
            st = await self.gateway.file_status(token, task_ids)
            vals = list(st.values())
            if vals and all(v in ("done", "error", "failed") for v in vals):
                return
            await asyncio.sleep(1.0)

    async def _run_streaming(self, chat_id, token, text, image_keys, message_id) -> None:
        state = {"steps": [], "answer": "", "notice": "", "seq": 0, "stop": False}
        card_id = await self.feishu.create_card_entity(streaming_card("正在思考…"))
        await self.feishu.send_card_entity(chat_id, card_id)
        flush = asyncio.create_task(self._flusher(card_id, state))
        try:
            if image_keys:
                state["notice"] = "正在识别图片…"
            task_ids = await self._prepare_attachments(token, image_keys, message_id)
            state["notice"] = ""
            msg = text or ("请描述并解释这张图片。" if task_ids else "")
            if not msg:
                state["answer"] = "图片识别失败，请重试，或改用文字描述。"
            else:
                async for ev in self.gateway.chat(token, msg, chat_id, task_ids):
                    t = ev.get("type")
                    if t == "step":
                        s = ev.get("text", "")
                        if s and (not state["steps"] or state["steps"][-1] != s):
                            state["steps"].append(s)
                    elif t == "delta":
                        state["answer"] += ev.get("text", "")
                    elif t == "error":
                        state["answer"] = f"出错了：{ev.get('text', '')}"
                        break
                    elif t == "done":
                        break
        except Exception as exc:
            logger.exception("流式对话失败: %s", exc)
            state["answer"] = f"出错了：{exc}"
        finally:
            await self._finalize(card_id, state, flush)

    async def _flusher(self, card_id: str, state: dict) -> None:
        last = None
        while not state["stop"]:
            await asyncio.sleep(FLUSH_INTERVAL)
            if state["stop"]:
                break
            text = build_stream_text(state["steps"], state["answer"], state["notice"])
            if text != last:
                state["seq"] += 1
                try:
                    await self.feishu.stream_card_text(card_id, ELEMENT_ID, text, state["seq"])
                    last = text
                except Exception as exc:
                    logger.warning("流式更新失败: %s", exc)

    async def _finalize(self, card_id: str, state: dict, flush) -> None:
        state["stop"] = True
        try:
            await flush
        except Exception:
            pass
        text = build_stream_text(state["steps"], state["answer"], state["notice"]) or "（无回复）"
        state["seq"] += 1
        try:
            await self.feishu.stream_card_text(card_id, ELEMENT_ID, text, state["seq"])
        except Exception as exc:
            logger.warning("最终刷新失败: %s", exc)
        state["seq"] += 1
        try:
            await self.feishu.close_card_stream(card_id, state["seq"])
        except Exception as exc:
            logger.warning("关闭流式失败: %s", exc)

    # ── 回退：整卡 patch（CardKit 不可用时） ──

    async def _run_patch(self, chat_id, token, text, image_keys, message_id) -> None:
        msg_id = await self.feishu.create_card(chat_id, thinking_card())
        steps: list[str] = []
        answer = ""
        last = 0.0
        try:
            task_ids = await self._prepare_attachments(token, image_keys, message_id)
            msg = text or ("请描述并解释这张图片。" if task_ids else "")
            if not msg:
                await self.feishu.patch_card(msg_id, error_card("图片识别失败，请重试或改用文字描述。"))
                return
            async for ev in self.gateway.chat(token, msg, chat_id, task_ids):
                t = ev.get("type")
                if t == "step":
                    s = ev.get("text", "")
                    if s and (not steps or steps[-1] != s):
                        steps.append(s)
                elif t == "delta":
                    answer += ev.get("text", "")
                elif t == "error":
                    await self.feishu.patch_card(msg_id, error_card(ev.get("text", "")))
                    return
                now = time.monotonic()
                if t in ("step", "done") or (now - last >= MIN_PATCH_INTERVAL):
                    await self.feishu.patch_card(msg_id, render(steps, answer))
                    last = now
        except Exception as exc:
            logger.exception("patch 流式失败: %s", exc)
            try:
                await self.feishu.patch_card(msg_id, error_card(str(exc)))
            except Exception:
                pass
            return
        await self.feishu.patch_card(msg_id, render(steps, answer or "（无回复）"))
