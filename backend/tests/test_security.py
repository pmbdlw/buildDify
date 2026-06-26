"""安全工具单测(无需数据库)。"""

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_password_over_72_bytes_does_not_error():
    # bcrypt 仅取前 72 字节,超长不应报错
    long_pw = "a" * 200
    h = hash_password(long_pw)
    assert verify_password(long_pw, h)


def test_jwt_roundtrip():
    token = create_access_token("user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
