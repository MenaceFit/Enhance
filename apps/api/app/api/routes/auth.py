from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import clear_session_cookie, get_optional_user, limit, set_session_cookie
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import hash_password, verify_password
from app.models import Photo, Project, User
from app.services import credits
from app.services.photos import retention_for
from app.services.privacy import record_consent

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=80)
    accept_privacy: bool


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def me_payload(db: Session, user: User | None) -> dict:
    if user is None:
        return {"user": None, "credits": None}
    s = credits.summary(db, user)
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "is_guest": user.is_guest,
            "is_admin": user.is_admin,
            "plan_code": user.plan_code,
            "preferences": user.preferences or {},
            "retention_days": user.retention_days or get_settings().default_retention_days,
            "created_at": user.created_at.isoformat(),
        },
        "credits": {
            "plan_code": s.plan_code,
            "plan_name": s.plan_name,
            "allowance": s.allowance,
            "used": s.used,
            "remaining": s.remaining,
            "period_end": s.period_end.isoformat(),
        },
    }


@router.get("/me")
def me(user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    return me_payload(db, user)


@router.post("/guest")
def guest(response: Response, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db),
          _=Depends(limit("auth", "rate_limit_auth_per_minute"))):
    if user is None:
        user = User(is_guest=True, plan_code="free")
        db.add(user)
        db.commit()
        set_session_cookie(response, user)
    return me_payload(db, user)


def _extend_retention(db: Session, user: User) -> None:
    expires = datetime.now(UTC) + retention_for(user)
    db.execute(update(Photo).where(Photo.user_id == user.id).values(expires_at=expires))


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, response: Response, current: User | None = Depends(get_optional_user),
           db: Session = Depends(get_db), _=Depends(limit("auth", "rate_limit_auth_per_minute"))):
    if not body.accept_privacy:
        raise HTTPException(422, "Merci d'accepter la politique de confidentialité.")
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Un compte existe déjà avec cet e-mail.")
    if current is not None and current.is_guest:
        user = current  # keep the photos improved as a guest
    else:
        user = User()
        db.add(user)
    user.email = email
    user.password_hash = hash_password(body.password)
    user.display_name = body.display_name
    user.is_guest = False
    user.plan_code = "free"
    user.is_admin = email in get_settings().admin_emails
    db.flush()
    record_consent(db, user, "privacy_policy", True)
    _extend_retention(db, user)
    db.commit()
    set_session_cookie(response, user)
    return me_payload(db, user)


@router.post("/login")
def login(body: LoginIn, response: Response, current: User | None = Depends(get_optional_user),
          db: Session = Depends(get_db), _=Depends(limit("auth", "rate_limit_auth_per_minute"))):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "E-mail ou mot de passe incorrect.")
    if current is not None and current.is_guest and current.id != user.id:
        # Bring the guest's photos into the account.
        db.execute(update(Project).where(Project.user_id == current.id).values(user_id=user.id))
        db.execute(update(Photo).where(Photo.user_id == current.id).values(user_id=user.id))
        db.delete(current)
    if user.email in get_settings().admin_emails:
        user.is_admin = True
    _extend_retention(db, user)
    db.commit()
    set_session_cookie(response, user)
    return me_payload(db, user)


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}
