"""
认证 — UUID Token

公网部署下每个请求都必须先回答「你是谁」：长期记忆按 user_id 打 payload、
会话按 user_id 归属。没有 user_id 就谈不上隔离。

做法是最简单的一种：注册时发一个 uuid4 token，客户端之后用
`Authorization: Bearer <token>` 带上。token 相当于「用户名 + 密码」合一，
所以有两点必须记住：

  - 只在 HTTPS 下暴露，否则 token 在链路上是裸奔的
  - 要能吊销 —— 删掉 users 表里那一行即可（见 session_store.revoke_token）

将来升级成真正的登录体系时，只需要替换 current_user 里的解析逻辑，
下游（记忆作用域、会话归属、配额）一行都不用改。
"""
from fastapi import Header, HTTPException

from src.storage.memory.session_store import get_user_by_token


def current_user(authorization: str = Header(default="")) -> dict:
    """FastAPI 依赖：从 `Authorization: Bearer <token>` 解析当前用户。

    刻意写成同步函数 —— FastAPI 会自动把它放进线程池执行，而
    get_user_by_token 是阻塞的 sqlite3 调用，不该占用事件循环。

    Returns:
        {"user_id": ..., "name": ..., "created_at": ...}

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
