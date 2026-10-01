from __future__ import annotations

import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_or_create_user, limit, require_user
from app.core.config import get_settings
from app.core.db import get_db
from app.imaging.image_io import ImageDecodeError
from app.imaging.settings import EnhancementSettings
from app.imaging.types import Analysis
from app.marketplaces import MARKETPLACES
from app.models import Job, Photo, PhotoVersion, Project, User
from app.services import credits
from app.services.jobs import create_job, enqueue, serialize_job
from app.services.photos import (
    UploadRejected,
    create_photo,
    default_project_name,
    preview_render,
    save_preview_as_version,
    serialize_photo,
    serialize_project,
    serialize_version,
)
from app.services.privacy import delete_photo

router = APIRouter(tags=["photos"])

ExportFormat = Literal["jpg", "png", "webp"]
ExportQuality = Literal["standard", "high", "max"]


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(404, "Introuvable.") from exc


def owned_photo(db: Session, user: User, photo_id: str) -> Photo:
    photo = db.scalar(
        select(Photo).options(selectinload(Photo.versions)).where(Photo.id == _uuid(photo_id), Photo.user_id == user.id)
    )
    if photo is None:
        raise HTTPException(404, "Photo introuvable.")
    return photo


def owned_project(db: Session, user: User, project_id: str) -> Project:
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.photos).selectinload(Photo.versions))
        .where(Project.id == _uuid(project_id), Project.user_id == user.id)
    )
    if project is None:
        raise HTTPException(404, "Projet introuvable.")
    return project


# --- upload ------------------------------------------------------------------------------------


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload(
    files: list[UploadFile] = File(...),
    project_id: str | None = Form(default=None),
    settings: str | None = Form(default=None),
    user: User = Depends(get_or_create_user),
    db: Session = Depends(get_db),
    _=Depends(limit("upload", "rate_limit_uploads_per_minute")),
):
    cfg = get_settings()
    if not files:
        raise HTTPException(422, "Aucune photo reçue.")
    if len(files) > cfg.max_photos_per_upload:
        raise HTTPException(422, f"Maximum {cfg.max_photos_per_upload} photos à la fois.")
    parsed_settings = None
    if settings:
        try:
            parsed_settings = EnhancementSettings(**json.loads(settings)).model_dump(mode="json")
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, "Réglages invalides.") from exc

    max_bytes = cfg.max_upload_mb * 1024 * 1024
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(413, f"{f.filename} : fichier trop lourd (max {cfg.max_upload_mb} Mo).")
        payloads.append((f.filename or "photo", data))

    if project_id:
        project = owned_project(db, user, project_id)
        if len(project.photos) + len(payloads) > cfg.max_photos_per_project:
            raise HTTPException(422, f"Une annonce peut contenir {cfg.max_photos_per_project} photos maximum.")
    else:
        project = Project(user_id=user.id, name=default_project_name())
        db.add(project)
        db.flush()

    try:
        credits.consume(db, user, len(payloads) * cfg.credit_cost_enhance)
    except credits.InsufficientCredits as exc:
        db.rollback()
        raise HTTPException(
            402,
            "Tu n'as plus assez de crédits." if exc.remaining else "Tu as utilisé tous tes crédits.",
        ) from exc

    start = (db.scalar(select(func.max(Photo.position)).where(Photo.project_id == project.id)) or 0) + 1
    photos, jobs = [], []
    try:
        for i, (name, data) in enumerate(payloads):
            photo = create_photo(db, user, project, start + i, name, data)
            photos.append(photo)
    except UploadRejected as exc:
        db.rollback()
        raise HTTPException(415, str(exc)) from exc
    db.flush()
    for photo in photos:
        jobs.append(create_job(db, "enhance", user_id=user.id, photo_id=photo.id, project_id=project.id,
                               params={"settings": parsed_settings, "charged": True}))
    db.commit()
    enqueue([j.id for j in jobs])
    db.refresh(project)
    return {
        "project": serialize_project(project, with_photos=False),
        "photos": [serialize_photo(p) for p in photos],
        "jobs": [serialize_job(j) for j in jobs],
    }


# --- projects ------------------------------------------------------------------------------------


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    consistency_enabled: bool | None = None
    marketplace: str | None = None


class EnhanceAllIn(BaseModel):
    settings: EnhancementSettings


class ExportIn(BaseModel):
    format: ExportFormat = "jpg"
    quality: ExportQuality = "standard"
    version_id: str | None = None


class OrderIn(BaseModel):
    photo_ids: list[str]


@router.get("/projects")
def list_projects(user: User = Depends(require_user), db: Session = Depends(get_db)):
    projects = db.scalars(
        select(Project).options(selectinload(Project.photos).selectinload(Photo.versions))
        .where(Project.user_id == user.id).order_by(Project.created_at.desc()).limit(200)
    ).all()
    return {"projects": [serialize_project(p, with_photos=False) for p in projects if p.photos]}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, user: User = Depends(get_or_create_user), db: Session = Depends(get_db)):
    p = Project(user_id=user.id, name=body.name)
    db.add(p)
    db.commit()
    return serialize_project(p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    data = serialize_project(project)
    active = db.scalars(
        select(Job).where(Job.project_id == project.id, Job.status.in_(("queued", "running")))
    ).all()
    data["active_jobs"] = [serialize_job(j) for j in active]
    return data


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatch, user: User = Depends(require_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    if body.name is not None:
        project.name = body.name
    if body.consistency_enabled is not None:
        project.consistency_enabled = body.consistency_enabled
    if body.marketplace is not None:
        if body.marketplace not in MARKETPLACES or not MARKETPLACES[body.marketplace].enabled:
            raise HTTPException(422, "Marketplace non disponible.")
        project.marketplace = body.marketplace
    db.commit()
    return serialize_project(project)


@router.put("/projects/{project_id}/order")
def reorder(project_id: str, body: OrderIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    by_id = {str(p.id): p for p in project.photos}
    if set(body.photo_ids) != set(by_id):
        raise HTTPException(422, "Liste de photos invalide.")
    for i, pid in enumerate(body.photo_ids, start=1):
        by_id[pid].position = i
    db.commit()
    db.refresh(project)
    return serialize_project(project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    for p in list(project.photos):
        delete_photo(db, p)
    db.delete(project)
    db.commit()


@router.post("/projects/{project_id}/enhance", status_code=202)
def enhance_all(project_id: str, body: EnhanceAllIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """"Améliorer toutes les photos" with one shared setting (+ consistency)."""
    project = owned_project(db, user, project_id)
    if not any(p.status == "ready" for p in project.photos):
        raise HTTPException(409, "Aucune photo prête.")
    job = create_job(db, "rerender", user_id=user.id, project_id=project.id,
                     params={"settings": body.settings.model_dump(mode="json")})
    db.commit()
    enqueue([job.id])
    return serialize_job(job)


@router.post("/projects/{project_id}/exports", status_code=202)
def export_project(project_id: str, body: ExportIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    job = create_job(db, "project_export", user_id=user.id, project_id=project.id,
                     params={"format": body.format, "quality": body.quality})
    db.commit()
    enqueue([job.id])
    return serialize_job(job)


# --- photos ----------------------------------------------------------------------------------------


class PhotoPatch(BaseModel):
    is_favorite: bool | None = None


class PreviewIn(BaseModel):
    settings: EnhancementSettings


class VersionIn(BaseModel):
    settings: EnhancementSettings
    label: str | None = Field(default=None, max_length=80)


class DefectPatch(BaseModel):
    status: Literal["acknowledged", "kept"]


@router.get("/photos")
def list_photos(
    favorites: bool = False,
    limit_: int = Query(default=60, alias="limit", ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    q = select(Photo).options(selectinload(Photo.versions)).where(Photo.user_id == user.id)
    if favorites:
        q = q.where(Photo.is_favorite.is_(True))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    photos = db.scalars(q.order_by(Photo.created_at.desc()).limit(limit_).offset(offset)).all()
    return {"photos": [serialize_photo(p) for p in photos], "total": total}


@router.get("/photos/{photo_id}")
def get_photo(photo_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = owned_photo(db, user, photo_id)
    data = serialize_photo(photo, detail=True)
    job = db.scalar(select(Job).where(Job.photo_id == photo.id).order_by(Job.created_at.desc()))
    data["latest_job"] = serialize_job(job) if job else None
    siblings = db.scalars(select(Photo.id).where(Photo.project_id == photo.project_id).order_by(Photo.position)).all()
    data["siblings"] = [str(s) for s in siblings]
    return data


@router.patch("/photos/{photo_id}")
def patch_photo(photo_id: str, body: PhotoPatch, user: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = owned_photo(db, user, photo_id)
    if body.is_favorite is not None:
        photo.is_favorite = body.is_favorite
    db.commit()
    return serialize_photo(photo)


@router.delete("/photos/{photo_id}", status_code=204)
def remove_photo(photo_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = owned_photo(db, user, photo_id)
    delete_photo(db, photo)
    db.commit()


@router.post("/photos/{photo_id}/retry", status_code=202)
def retry_photo(photo_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = owned_photo(db, user, photo_id)
    if photo.status != "failed":
        raise HTTPException(409, "Cette photo n'est pas en échec.")
    try:
        credits.consume(db, user, get_settings().credit_cost_enhance, photo_ids=[photo.id])
    except credits.InsufficientCredits as exc:
        raise HTTPException(402, "Tu as utilisé tous tes crédits.") from exc
    photo.status, photo.error = "queued", None
    job = create_job(db, "enhance", user_id=user.id, photo_id=photo.id, project_id=photo.project_id, params={"charged": True})
    db.commit()
    enqueue([job.id])
    return serialize_job(job)


def _require_ready(photo: Photo) -> None:
    if photo.status != "ready":
        raise HTTPException(409, "La photo est encore en cours de traitement.")


@router.post("/photos/{photo_id}/preview")
def preview(photo_id: str, body: PreviewIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Live editor preview (synchronous, cached per settings)."""
    photo = owned_photo(db, user, photo_id)
    _require_ready(photo)
    try:
        return preview_render(photo, body.settings)
    except ImageDecodeError as exc:
        raise HTTPException(409, "Photo indisponible.") from exc


@router.post("/photos/{photo_id}/versions", status_code=201)
def create_version(photo_id: str, body: VersionIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = owned_photo(db, user, photo_id)
    _require_ready(photo)
    v = save_preview_as_version(db, photo, body.settings, kind="edited", label=body.label)
    db.commit()
    return serialize_version(v)


@router.post("/photos/{photo_id}/versions/{version_id}/restore")
def restore_version(photo_id: str, version_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = owned_photo(db, user, photo_id)
    v = db.get(PhotoVersion, _uuid(version_id))
    if v is None or v.photo_id != photo.id:
        raise HTTPException(404, "Version introuvable.")
    photo.current_version_id = v.id
    db.commit()
    return serialize_photo(photo, detail=True)


@router.patch("/photos/{photo_id}/defects/{defect_id}")
def patch_defect(photo_id: str, defect_id: str, body: DefectPatch, user: User = Depends(require_user),
                 db: Session = Depends(get_db)):
    photo = owned_photo(db, user, photo_id)
    ids = {d["id"] for d in (photo.analysis or {}).get("defects", [])}
    if defect_id not in ids:
        raise HTTPException(404, "Zone introuvable.")
    photo.defect_state = {**(photo.defect_state or {}), defect_id: body.status}
    db.commit()
    return {"defect_state": photo.defect_state}


@router.post("/photos/{photo_id}/exports", status_code=202)
def export_photo(photo_id: str, body: ExportIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = owned_photo(db, user, photo_id)
    _require_ready(photo)
    job = create_job(db, "export", user_id=user.id, photo_id=photo.id, project_id=photo.project_id,
                     params={"format": body.format, "quality": body.quality, "version_id": body.version_id})
    db.commit()
    enqueue([job.id])
    return serialize_job(job)


@router.get("/photos/{photo_id}/listing")
def listing(photo_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """V2 preview: listing draft (title, description, keywords) from the photo."""
    from app.core.storage import get_storage
    from app.imaging.image_io import decode_rgb_fast, resize_long_side
    from app.providers.base import Capability
    from app.providers.registry import get_router

    photo = owned_photo(db, user, photo_id)
    _require_ready(photo)
    analysis = Analysis.from_dict(photo.analysis)
    router = get_router()
    img = resize_long_side(decode_rgb_fast(get_storage().get(photo.working_key)), 1568)
    provider = router.provider_for(Capability.LISTING)
    if provider.name == "local":
        from app.services.listing import listing_from_attributes

        return listing_from_attributes(analysis.clothing, analysis.defects)
    return router.call(Capability.LISTING, "generate_listing", img, analysis.clothing)


# --- jobs & dashboard --------------------------------------------------------------------------------


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    job = db.get(Job, _uuid(job_id))
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "Tâche introuvable.")
    return serialize_job(job)


@router.get("/jobs")
def get_jobs(ids: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    wanted = [_uuid(i) for i in ids.split(",") if i][:50]
    jobs = db.scalars(select(Job).where(Job.id.in_(wanted), Job.user_id == user.id)).all()
    return {"jobs": [serialize_job(j) for j in jobs]}


@router.get("/dashboard")
def dashboard(user: User = Depends(require_user), db: Session = Depends(get_db)):
    cfg = get_settings()
    enhanced = db.scalar(select(func.count()).select_from(Photo).where(Photo.user_id == user.id, Photo.status == "ready")) or 0
    s = credits.summary(db, user)
    recent = db.scalars(
        select(Photo).options(selectinload(Photo.versions)).where(Photo.user_id == user.id)
        .order_by(Photo.created_at.desc()).limit(8)
    ).all()
    projects = db.scalars(
        select(Project).options(selectinload(Project.photos).selectinload(Photo.versions))
        .where(Project.user_id == user.id).order_by(Project.created_at.desc()).limit(4)
    ).all()
    return {
        "photos_enhanced": enhanced,
        "credits": {"remaining": s.remaining, "allowance": s.allowance, "plan_name": s.plan_name},
        "minutes_saved": round(enhanced * cfg.minutes_saved_per_photo),
        "recent_photos": [serialize_photo(p) for p in recent],
        "recent_projects": [serialize_project(p, with_photos=False) for p in projects if p.photos],
    }
