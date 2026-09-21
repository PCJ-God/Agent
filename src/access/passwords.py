"""
密码哈希 — 标准库 scrypt

为什么用 stdlib 而不是 bcrypt / argon2：
  1. **不引入新依赖**。本项目的依赖是钉死在 `constraints.txt` 里的实测组合
     （110 个包），每加一个包都要在 Python 3.14 上重新验证一遍，而 PyPI 只走
     国内镜像（见 docs/DEPLOY.md）。
  2. scrypt 是**内存硬**（memory-hard）的 KDF，抗 GPU/ASIC 暴力破解，
     强度足以承担这个场景。
  3. `hashlib.scrypt` 自 Python 3.6 起就在标准库里（依赖 OpenSSL 1.1+），
     不需要编译扩展 —— 在 Python 3.14 这种新版本上这点尤其省事。

存储格式是**自描述**的，便于将来换算法而不用让存量用户改密码：

    scrypt$n=16384,r=8,p=1$<salt_b64>$<hash_b64>

将来迁到 argon2 时，按前缀分派校验逻辑即可（`verify_password` 已经是这个结构）。
"""
import base64
import hashlib
import hmac
import re
import secrets

#: 算法标识，写在存储串的最前面
_ALGO = "scrypt"

#: scrypt 代价参数。n=16384 约需 16 MB 内存、单次约几十毫秒 ——
#: 对登录接口可接受，对离线爆破则足够贵。
_N = 16384
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16

#: 密码长度上限。没有上限的话，一个超长请求就能让 scrypt 变成 DoS 手段。
MAX_PASSWORD_LEN = 128
MIN_PASSWORD_LEN = 8

#: 用户名规则：3-32 个字符，允许字母、数字、下划线、点、横线，
#: `\w` 在 Python 3 下也匹配中文，所以中文用户名可用。
USERNAME_RE = re.compile(r"^[\w.-]{3,32}$", re.UNICODE)


def normalise_username(username: str) -> str:
    """用户名归一化（用于查重与登录查找）。

    统一转小写，所以 `Alice` 与 `alice` 是同一个账号。
    展示时用的是用户原始输入（存在 users.name 里）。
    """
    return (username or "").strip().lower()


def username_error(username: str) -> str | None:
    """校验用户名格式，合法返回 None，否则返回给用户看的错误说明。"""
    u = normalise_username(username)
    if not u:
        return "用户名不能为空"
    if not USERNAME_RE.match(u):
        return "用户名需为 3-32 个字符，只能用字母、数字、下划线、点或横线"
    return None


def password_error(password: str) -> str | None:
    """校验密码强度，合法返回 None。"""
    if not password:
        return "密码不能为空"
    if len(password) < MIN_PASSWORD_LEN:
        return f"密码至少 {MIN_PASSWORD_LEN} 位"
    if len(password) > MAX_PASSWORD_LEN:
        return f"密码不能超过 {MAX_PASSWORD_LEN} 位"
    return None


def hash_password(password: str) -> str:
    """把明文密码变成可存储的字符串。每次调用都生成新 salt。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN
    )
    return "{}$n={},r={},p={}${}${}".format(
        _ALGO,
        _N,
        _R,
        _P,
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    """校验密码。

    任何异常（存储串为空、格式不对、算法不认识、参数非法）一律返回 False，
    不向外抛 —— 认证失败不该变成一个 500。
    """
    if not password or not stored:
        return False
    try:
        algo, params, salt_b64, hash_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        kv = dict(item.split("=", 1) for item in params.split(","))
        n, r, p = int(kv["n"]), int(kv["r"]), int(kv["p"])
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except Exception:
        return False

    try:
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected)
        )
    except Exception:
        return False

    # 定长比较，避免按字节早退泄露信息
    return hmac.compare_digest(dk, expected)


def burn_time() -> None:
    """用户名不存在时也要烧掉等价的时间。

    否则「账号不存在」立刻返回、而「密码错误」要算完一次 scrypt 才返回，
    这个时间差可以被用来枚举账号。在登录失败路径上调用它把两条路拉平。
    """
    hash_password("timing-equalisation-dummy")
