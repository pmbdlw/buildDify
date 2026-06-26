"""安全工具单测(无需数据库)。"""

from app.core.security import (
    API_KEY_PREFIX,
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
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


def test_api_key_generate_and_hash():
    raw, prefix, key_hash = generate_api_key()
    assert raw.startswith(API_KEY_PREFIX)
    assert raw.startswith(prefix)
    assert key_hash == hash_api_key(raw)
    assert len(key_hash) == 64  # sha256 十六进制


def test_api_keys_are_unique():
    raw1, _, hash1 = generate_api_key()
    raw2, _, hash2 = generate_api_key()
    assert raw1 != raw2
    assert hash1 != hash2
