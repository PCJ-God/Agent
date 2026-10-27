"""feishu-adapter 入口：长连接接收消息事件。

长连接客户端内部用模块级 asyncio 事件循环；启动前在同一循环里预取机器人
open_id（群聊 @ 过滤用），然后调用阻塞的 cli.start() 常驻运行。
"""
from __future__ import annotations

import asyncio
import logging

import lark_oapi as lark

from app.bot import Bot
from app.config import FEISHU_APP_ID, FEISHU_APP_SECRET


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logging.error("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置，请在 .env 中填写后重启")
        return

    bot = Bot()

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(bot.on_message)
        .build()
    )

    cli = lark.ws.Client(
        FEISHU_APP_ID,
        FEISHU_APP_SECRET,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot.start())

    cli.start()


if __name__ == "__main__":
    main()
