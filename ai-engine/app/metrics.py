"""Prometheus 指标（Phase 7）。

用标准库手写 text 格式，不引入 prometheus-client 依赖。
只统计「累计 HTTP 请求数」，满足监控埋点的最小闭环。
"""
import threading
from collections import defaultdict

_counter: dict[str, int] = defaultdict(int)
_lock = threading.Lock()


def inc(path: str) -> None:
    with _lock:
        _counter[path] += 1


def render() -> str:
    lines = [
        "# HELP http_requests_total 累计 HTTP 请求数",
        "# TYPE http_requests_total counter",
    ]
    with _lock:
        for path, n in sorted(_counter.items()):
            lines.append(f'http_requests_total{{path="{path}"}} {n}')
    return "\n".join(lines) + "\n"
