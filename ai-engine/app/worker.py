"""异步文档解析 worker。

消费 RabbitMQ `doc_parse` 队列：
- 下载 MinIO 文件 → 问题理解层解析（docx/pdf/OCR）
- task_type=chat：解析结果写 Redis（ai-engine 按 task_id 读取）
- task_type=ingest：额外调 gRPC IngestText 写入知识库
用 `python -m app.worker` 启动（独立进程，见 docker-compose ai-worker 服务）。
"""
import json
import logging
import time

import grpc
import httpx
import pika
import redis

from app import understanding
from app.config import PARSE_RESULT_TTL, RABBITMQ_URL, REDIS_URL
from gen import assistant_pb2, assistant_pb2_grpc

QUEUE = "doc_parse"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("worker")


def _redis() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _set_result(task_id: str, status: str, text: str = "") -> None:
    r = _redis()
    r.set(f"parse:status:{task_id}", status, ex=PARSE_RESULT_TTL)
    if text:
        r.set(f"parse:{task_id}", text, ex=PARSE_RESULT_TTL)


def _ingest_to_kb(name: str, text: str, source: str) -> int:
    channel = grpc.insecure_channel("ai-engine:50051")
    try:
        stub = assistant_pb2_grpc.AssistantServiceStub(channel)
        resp = stub.IngestText(
            assistant_pb2.IngestTextRequest(name=name, text=text, source=source)
        )
        return resp.ingested
    finally:
        channel.close()


def handle(ch, method, _properties, body):
    msg = json.loads(body)
    task_id = msg.get("task_id", "")
    filename = msg.get("filename", "upload")
    task_type = msg.get("task_type", "chat")
    object_key = msg.get("object_key", "")
    try:
        resp = httpx.get(msg["download_url"], timeout=60)
        resp.raise_for_status()
        text, meta = understanding.parse(filename, resp.content)
        _set_result(task_id, "done", text)
        logger.info("解析完成 %s（%s，%d 字符）", filename, meta["type"], len(text))
        if task_type == "ingest":
            n = _ingest_to_kb(object_key, text, source=filename)
            logger.info("入库 %s -> %d 切片", filename, n)
    except Exception as exc:
        logger.error("解析失败 %s: %s", object_key, exc)
        _set_result(task_id, "error", str(exc))
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
