"""飞书卡片（schema 2.0）构建 + CardKit 流式卡片。"""
import json

HEADER_TITLE = "ACP Copilot 学习助手"
ELEMENT_ID = "md"  # 流式卡片里承载正文的 markdown 组件 id


def _card(markdown: str) -> str:
    return json.dumps(
        {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": HEADER_TITLE},
                "template": "blue",
            },
            "body": {"elements": [{"tag": "markdown", "content": markdown}]},
        },
        ensure_ascii=False,
    )


def thinking_card() -> str:
    return _card("正在思考…")


def render(steps: list[str], answer: str) -> str:
    parts = []
    for s in steps:
        parts.append(f"> {s}")
    if parts:
        parts.append("")
    parts.append(answer or "正在思考…")
    return _card("\n".join(parts))


def error_card(text: str) -> str:
    return _card(f"出错了：{text}")


def not_bound_card() -> str:
    return _card(
        "你还没有绑定 Web 账号。\n\n"
        "请先到 Web 端注册并登录，然后 @我发送「绑定」获取验证码，"
        "再回到 Web 端「飞书绑定」页完成绑定。"
    )


def streaming_card(text: str = "正在思考…") -> str:
    """创建带 element_id 的流式卡片实体 JSON（streaming_mode 打开）。"""
    card = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "streaming_mode": True,
            "summary": {"content": HEADER_TITLE},
            "streaming_config": {
                "print_frequency_ms": {"default": 50, "android": 50, "ios": 50, "pc": 50},
                "print_step": {"default": 1, "android": 1, "ios": 1, "pc": 1},
                "print_strategy": "fast",
            },
        },
        "header": {
            "title": {"tag": "plain_text", "content": HEADER_TITLE},
            "template": "blue",
        },
        "body": {"elements": [{"tag": "markdown", "content": text, "element_id": ELEMENT_ID}]},
    }
    return json.dumps(card, ensure_ascii=False)


def build_stream_text(steps: list[str], answer: str, notice: str = "") -> str:
    """把工具轨迹(step) + 正文拼成流式卡片展示文本。"""
    parts = [f"> {s}" for s in steps]
    body = answer or notice or "正在思考…"
    if parts:
        return "\n".join(parts) + "\n\n" + body
    return body
