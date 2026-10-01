"""GDPR: erasure, retention purge, consent records."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.storage import get_storage, user_prefix
from app.models import Consent, Job, Photo, User
from app.services.photos import source_cache

log = logging.getLogger(__name__)


def delete_photo(db: Session, photo: Photo) -> None:
    get_storage().delete_prefix(photo.storage_prefix)
    source_cache.drop(photo.id)
    db.delete(photo)


def delete_account(db: Session, user: User) -> int:
    """Erase every file and row belonging to the user (right to erasure)."""
    st = get_storage()
    prefix = user_prefix(user.id)
    removed = st.delete_prefix(prefix)
    # photos inherited from a guest session keep their original storage prefix
    for p in db.scalars(select(Photo).where(Photo.user_id == user.id)):
        if not p.storage_prefix.startswith(prefix):
            removed += st.delete_prefix(p.storage_prefix)
    db.execute(delete(Job).where(Job.user_id == user.id))
    db.delete(user)
    log.info("account %s erased (%s files)", user.id, removed)
    return removed


def record_consent(db: Session, user: User, kind: str, granted: bool) -> Consent:
    c = Consent(user_id=user.id, kind=kind, granted=granted, version=get_settings().privacy_policy_version)
    db.add(c)
    return c


def latest_consents(db: Session, user: User) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for c in db.scalars(select(Consent).where(Consent.user_id == user.id).order_by(Consent.created_at)):
        out[c.kind] = c.granted
    return out


def purge_expired(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Retention: expired photos, stale guest accounts, temporary renders and old exports."""
    cfg = get_settings()
    now = now or datetime.now(UTC)
    st = get_storage()
    photos = list(db.scalars(select(Photo).where(Photo.expires_at.is_not(None), Photo.expires_at < now).limit(500)))
    for p in photos:
        delete_photo(db, p)
    guests_cutoff = now - timedelta(days=cfg.guest_retention_days)
    guests = list(db.scalars(select(User).where(User.is_guest.is_(True), User.created_at < guests_cutoff).limit(500)))
    for g in guests:
        delete_account(db, g)
    db.commit()
    # temporary editor renders and exports older than a day
    _purge_temporary(st, db, now - timedelta(days=1))
    return {"photos": len(photos), "guests": len(guests)}


def _purge_temporary(st, db: Session, cutoff: datetime) -> None:
    """Exports and editor preview renders are temporary.

    On S3/R2, configure a lifecycle rule expiring ``*/renders/*`` after 1 day; the
    local backend is swept here.
    """
    import shutil

    from app.core.storage import LocalStorage
    from app.models import Export

    for e in db.scalars(select(Export).where(Export.created_at < cutoff).limit(1000)):
        st.delete(e.key)
        db.delete(e)
    db.commit()
    if isinstance(st, LocalStorage):
        users_dir = st.path_for("users")
        if users_dir.is_dir():
            for renders in users_dir.glob("*/photos/*/renders/*"):
                if renders.is_dir() and datetime.fromtimestamp(renders.stat().st_mtime, UTC) < cutoff:
                    shutil.rmtree(renders, ignore_errors=True)
