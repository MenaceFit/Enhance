"""Passwords, session tokens, rate limiting."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_session_token(user_id: uuid.UUID, token_version: int, *, guest: bool) -> str:
    cfg = get_settings()
    now = datetime.now(UTC)
    ttl = timedelta(days=cfg.guest_retention_days if guest else cfg.session_ttl_days)
    payload = {"sub": str(user_id), "ver": token_version, "guest": guest, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, cfg.secret_key, algorithm="HS256")


def decode_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


class RateLimiter:
    """Sliding-window limiter keyed by (bucket, client). In-process; put a shared
    limiter (Redis, API gateway) in front when running several API replicas."""

    def __init__(self):
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, bucket: str, client: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[(bucket, client)]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()
