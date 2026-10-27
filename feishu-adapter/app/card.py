"""飞书卡片（schema 2.0）构建。"""
import json

HEADER_TITLE = "ACP Copilot 学习助手"


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
