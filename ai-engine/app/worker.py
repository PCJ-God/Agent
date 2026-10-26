"""异步文档解析 worker（Phase 6）。

消费 RabbitMQ 的 doc_parse 队列：下载上传的文件 -> 解析文本 -> 分块向量化 -> 写入 Chroma。
用 `python -m app.worker` 启动（独立于 uvicorn 进程，见 docker-compose ai-worker 服务）。
"""
import json
import logging
import time

import httpx
import pika

from app import rag
from app.config import RABBITMQ_URL

QUEUE = "doc_parse"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("worker")


def parse_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith((".md", ".txt", ".json", ".csv", ".log")):
        return content.decode("utf-8", errors="ignore")
    return None  # 不支持的类型


def handle(ch, method, _properties, body):
    msg = json.loads(body)
    object_key = msg["object_key"]
    filename = msg.get("filename", "upload")
    try:
        resp = httpx.get(msg["download_url"], timeout=60)
        resp.raise_for_status()
        text = parse_text(filename, resp.content)
        if text is None:
            logger.warning("跳过不支持的类型: %s", filename)
        else:
            result = rag.ingest_text(object_key, text, source=filename)
            logger.info("摄入 %s -> %s", filename, result)
    except Exception as exc:
        logger.error("解析失败 %s: %s", object_key, exc)
    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    params = pika.URLParameters(RABBITMQ_URL)
    while True:
        try:
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.queue_declare(queue=QUEUE, durable=True)
            ch.basic_qos(prefetch_count=1)
            ch.basic_consume(queue=QUEUE, on_message_callback=handle)
            logger.info("worker 已就绪，等待 doc_parse 任务...")
            ch.start_consuming()
        except Exception as exc:
            logger.error("连接异常，5s 后重试: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
