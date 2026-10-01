"""Request dependencies: session, authorisation, rate limiting."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_session_token, decode_session_token, rate_limiter
from app.models import User


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def set_session_cookie(response: Response, user: User) -> None:
    set_session_cookie_raw(response, user.id, user.token_version, guest=user.is_guest)


def set_session_cookie_raw(response: Response, user_id: uuid.UUID, token_version: int, *, guest: bool) -> None:
    cfg = get_settings()
    token = create_session_token(user_id, token_version, guest=guest)
    days = cfg.guest_retention_days if guest else cfg.session_ttl_days
    response.set_cookie(
        cfg.session_cookie_name, token, max_age=days * 86400, httponly=True, secure=cfg.cookie_secure,
        samesite="lax", path="/",
    )


def clear_session_cookie(response: Response) -> None:
    cfg = get_settings()
    response.delete_cookie(cfg.session_cookie_name, path="/", httponly=True, secure=cfg.cookie_secure, samesite="lax")


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    payload = decode_session_token(token)
    if not payload:
        return None
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (KeyError, ValueError):
        return None
    if user is None or user.token_version != payload.get("ver"):
        return None
    now = datetime.now(UTC)
    last = user.last_seen_at.replace(tzinfo=UTC) if user.last_seen_at and user.last_seen_at.tzinfo is None else user.last_seen_at
    if last is None or now - last > timedelta(minutes=10):
        user.last_seen_at = now
        db.commit()
    return user


def require_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Connexion requise.")
    return user


def require_registered(user: User = Depends(require_user)) -> User:
    if user.is_guest:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Crée un compte pour accéder à cette fonctionnalité.")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès réservé aux administrateurs.")
    return user


def get_or_create_user(
    request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)
) -> User:
    """Anonymous visitors get a guest account on their first upload: no sign-up wall.

    The session cookie is attached by the HTTP middleware (``request.state.new_session``)
    so that it is also sent with error responses (e.g. 402 on the very first upload).
    """
    if user is not None:
        return user
    if not rate_limiter.allow("guest", client_ip(request), 10, 3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Trop de sessions créées. Réessaie plus tard.")
    user = User(is_guest=True, plan_code="free")
    db.add(user)
    db.commit()
    request.state.new_session = (user.id, user.token_version)
    return user


def limit(bucket: str, per_minute_setting: str):
    def dep(request: Request) -> None:
        cfg = get_settings()
        if not rate_limiter.allow(bucket, client_ip(request), getattr(cfg, per_minute_setting)):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Trop de requêtes. Réessaie dans un instant.")

    return dep
