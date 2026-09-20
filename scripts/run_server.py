#!/usr/bin/env python
"""
Agent Web Backend — FastAPI + 层级协作模式 (Hierarchical)

架构: 接入层(FastAPI) → 调度层(Leader) → 执行层(Researcher + Reviewer + MCP + Skills)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.access.server import run

if __name__ == "__main__":
    run()