"""feishu-adapter 配置。"""
import os

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")
INTERNAL_TOKEN = os.getenv("FEISHU_ADAPTER_TOKEN", "")
