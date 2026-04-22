"""hydra.core.auth — bcrypt password + JWT session token."""
import pytest

from hydra.core.auth import (
    hash_password, verify_password,
    create_session_token, verify_session_token,
)


def test_hash_password_returns_different_string_than_plain():
    plain = "MyStrong!Pass2026"
    hashed = hash_password(plain)
    assert hashed != plain
    assert hashed.startswith("$2")  # bcrypt hash format


def test_verify_password_roundtrip():
    plain = "MyStrong!Pass2026"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong_pw", hashed) is False


def test_verify_password_with_invalid_hash_returns_false():
    assert verify_password("anything", "not_a_bcrypt_hash") is False


def test_hash_password_produces_different_hashes_same_input():
    """bcrypt 는 salt 로 매번 다른 해시 생성."""
    a = hash_password("same_input")
    b = hash_password("same_input")
    assert a != b
    assert verify_password("same_input", a)
    assert verify_password("same_input", b)


def test_session_token_roundtrip():
    secret = "test-jwt-secret-1234"
    token = create_session_token(user_id=42, role="admin", secret=secret)
    assert isinstance(token, str)
    assert token.count(".") == 2  # JWT 는 3 part (header.payload.sig)

    data = verify_session_token(token, secret=secret)
    assert data["user_id"] == 42
    assert data["role"] == "admin"
    assert "exp" in data  # 만료 claim 존재


def test_session_token_wrong_secret_rejected():
    secret = "correct-secret"
    token = create_session_token(user_id=1, role="admin", secret=secret)
    with pytest.raises(Exception):
        verify_session_token(token, secret="wrong-secret")


def test_session_token_tampered_rejected():
    """토큰 일부 문자 바꾸면 서명 불일치로 거절."""
    secret = "s"
    token = create_session_token(user_id=1, role="admin", secret=secret)
    # payload 부분 (중간) 문자 하나 바꿈
    parts = token.split(".")
    tampered = parts[0] + "." + parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B") + "." + parts[2]
    with pytest.raises(Exception):
        verify_session_token(tampered, secret=secret)
