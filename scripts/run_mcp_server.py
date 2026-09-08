#!/usr/bin/env python
"""
运行 MCP Server
本地模拟 WebSearch 服务，用于开发调试
"""
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.web_search_server import mcp


def main():
    print("启动 WebSearch MCP Server (stdio 模式)...")
    print("等待 Client 连接...\n")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
