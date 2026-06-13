"""Password hashing (argon2) + JWT access tokens (HS256) for SAMpai app users.

Distinct from the LightRAG server's own AuthHandler — SAMpai users live in the
app database, not the AUTH_ACCOUNTS env list.
"""

from __future__ import annotations

import datetime as _dt

import jwt
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["argon2"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(*, user_id: int, secret: str, expire_minutes: int) -> str:
    now = _dt.datetime.now(_dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + _dt.timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
