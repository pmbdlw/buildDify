"""密码哈希与 JWT 编解码;应用对外调用的 API Key 生成与哈希。"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

API_KEY_PREFIX = "bd-"  # buildDify 应用密钥前缀


def _to_bytes(password: str) -> bytes:
    # bcrypt 仅取前 72 字节;超长部分按其规范截断。
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(_to_bytes(password), password_hash.encode("utf-8"))


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def generate_api_key() -> tuple[str, str, str]:
    """生成应用 API Key,返回 (明文, 展示前缀, sha256 哈希)。

    明文形如 bd-<43位 urlsafe>,仅在创建时返回一次;库里只存前缀与哈希。
    API Key 为高熵随机串,用 sha256 哈希足够(无需 bcrypt 的慢哈希)。
    """
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:11], hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
