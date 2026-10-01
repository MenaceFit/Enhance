"""Account settings and GDPR rights (access/portability, erasure, consent)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import clear_session_cookie, require_registered, require_user
from app.api.routes.auth import _extend_retention, me_payload
from app.core.config import get_settings
from app.core.db import get_db
from app.imaging.settings import Intensity
from app.models import User
from app.services.jobs import create_job, enqueue, serialize_job
from app.services.privacy import delete_account, latest_consents, record_consent

router = APIRouter(prefix="/account", tags=["account"])


class AccountPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    retention_days: int | None = Field(default=None, ge=1, le=365)
    default_intensity: Intensity | None = None
    default_preserve: bool | None = None


class ConsentIn(BaseModel):
    kind: Literal["analytics", "marketing"]
    granted: bool


class DeleteIn(BaseModel):
    confirm: str


@router.get("")
def get_account(user: User = Depends(require_user), db: Session = Depends(get_db)):
    data = me_payload(db, user)
    data["consents"] = latest_consents(db, user)
    data["privacy_policy_version"] = get_settings().privacy_policy_version
    return data


@router.patch("")
def patch_account(body: AccountPatch, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if body.display_name is not None:
        user.display_name = body.display_name or None
    prefs = dict(user.preferences or {})
    if body.default_intensity is not None:
        prefs["default_intensity"] = body.default_intensity
    if body.default_preserve is not None:
        prefs["default_preserve"] = body.default_preserve
    user.preferences = prefs
    if body.retention_days is not None:
        if user.is_guest:
            raise HTTPException(403, "Crée un compte pour choisir la durée de conservation.")
        user.retention_days = min(body.retention_days, get_settings().max_retention_days)
        _extend_retention(db, user)
    db.commit()
    return get_account(user, db)


@router.post("/consents")
def set_consent(body: ConsentIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    record_consent(db, user, body.kind, body.granted)
    db.commit()
    return {"consents": latest_consents(db, user)}


@router.post("/export", status_code=202)
def export_data(user: User = Depends(require_registered), db: Session = Depends(get_db)):
    job = create_job(db, "gdpr_export", user_id=user.id)
    db.commit()
    enqueue([job.id])
    return serialize_job(job)


@router.post("/delete")
def erase_account(body: DeleteIn, response: Response, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if body.confirm.strip().upper() != "SUPPRIMER":
        raise HTTPException(422, "Tape SUPPRIMER pour confirmer.")
    delete_account(db, user)
    db.commit()
    clear_session_cookie(response)
    return {"deleted": True}
