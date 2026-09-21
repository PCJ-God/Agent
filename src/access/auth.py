"""
认证 — UUID Token

公网部署下每个请求都必须先回答「你是谁」：长期记忆按 user_id 打 payload、
会话按 user_id 归属。没有 user_id 就谈不上隔离。

拿到 token 有两种方式：匿名（register 直接发）与具名（login 用
「用户名 + 密码」换）。客户端之后都用 `Authorization: Bearer <token>` 带上。

token 本身仍是「一票通行」的凭证，所以有两点必须记住：

  - 只在 HTTPS 下暴露，否则 token 在链路上是裸奔的
  - 要能吊销：POST /api/auth/logout 删掉 tokens 表里那一条
    （见 session_store.revoke_token；同账号其他设备不受影响）

解析逻辑全部收在下面两个函数里，下游（记忆作用域、会话归属、配额）只依赖
返回的 user_id，所以换认证方式时那边一行都不用改。
"""
from fastapi import Header, HTTPException

from src.storage.memory.session_store import get_user_by_token


def current_user(authorization: str = Header(default="")) -> dict:
    """FastAPI 依赖：从 `Authorization: Bearer <token>` 解析当前用户。

    刻意写成同步函数 —— FastAPI 会自动把它放进线程池执行，而
    get_user_by_token 是阻塞的 sqlite3 调用，不该占用事件循环。

    Returns:
        {"user_id": ..., "name": ..., "created_at": ..., "username": ...,
         "is_anonymous": ...}

    Raises:
        HTTPException: 401（缺少凭证 / token 无效或已吊销）
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="缺少凭证：请先 POST /api/auth/register 获取 token，"
                   "再用 Authorization: Bearer <token> 访问",
        )
    user = get_user_by_token(authorization[7:].strip())
    if user is None:
        raise HTTPException(status_code=401, detail="token 无效或已吊销")
    return user


def bearer_token(authorization: str = Header(default="")) -> str:
    """FastAPI 依赖：取出 `Authorization: Bearer <token>` 里的 token 原文。

    登出要拿原文才能吊销，而 current_user 返回的是用户信息（刻意不含 token）。
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少凭证")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="缺少凭证")
    return token
