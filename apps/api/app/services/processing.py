"""Job handlers: the work done by queue workers."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.storage import get_storage, user_prefix
from app.imaging.consistency import harmonize
from app.imaging.image_io import (
    MIME_BY_FORMAT,
    ImageDecodeError,
    decode_image,
    encode_image,
    encode_mask,
    resize_long_side,
)
from app.imaging.pipeline import analyze, enhance
from app.imaging.render import RenderSource
from app.imaging.settings import EnhancementSettings
from app.imaging.types import Analysis, StageRecord
from app.marketplaces import export_filename, get_marketplace
from app.models import (
    BenchmarkRun,
    Consent,
    CreditTransaction,
    Export,
    Job,
    Photo,
    PhotoVersion,
    Project,
    ProviderCall,
    Subscription,
    User,
)
from app.providers.registry import get_providers, get_router
from app.services import credits
from app.services.jobs import JobError, handler
from app.services.photos import (
    current_version,
    jsonable,
    load_source,
    save_version,
    serialize_version,
    source_cache,
)


def _record_calls(db: Session, job: Job, stages: list[StageRecord]) -> None:
    total = 0.0
    for s in stages:
        if s.provider and s.name in {
            "segmentation", "clothing_detection", "dust_detection", "defect_detection", "enhancement", "upscaling", "listing",
        }:
            db.add(
                ProviderCall(
                    job_id=job.id, capability=s.name, provider=s.provider, model=s.model, duration_ms=s.duration_ms,
                    cost_cents=s.cost_cents, success=bool(s.details.get("success", True)), error=s.details.get("error"),
                )
            )
            total += s.cost_cents
    job.cost_cents = round((job.cost_cents or 0) + total, 4)


def _settings_for(user: User, params: dict) -> EnhancementSettings:
    if params.get("settings"):
        return EnhancementSettings(**params["settings"])
    prefs = user.preferences or {}
    return EnhancementSettings(
        intensity=prefs.get("default_intensity", "naturel"),
        preserve_article=prefs.get("default_preserve", True),
    )


# --- enhance: decode → analyse → AI render ---------------------------------------------------


def _enhance_failed(db: Session, job: Job, exc: Exception) -> None:
    photo = db.get(Photo, job.photo_id) if job.photo_id else None
    if photo is not None:
        photo.status = "failed"
        photo.error = job.error
    if job.user_id and job.params.get("charged", True):
        credits.refund(db, job.user_id, job.photo_id, job.id)


@handler("enhance", on_failure=_enhance_failed)
def run_enhance(db: Session, job: Job, progress) -> dict:
    cfg = get_settings()
    st = get_storage()
    photo = db.get(Photo, job.photo_id)
    if photo is None:
        raise JobError("Photo introuvable.")
    user = db.get(User, photo.user_id)
    photo.status = "processing"
    progress("decode", "Préparation de la photo", 0.01)

    try:
        decoded = decode_image(st.get(photo.original_key))
    except ImageDecodeError as exc:
        raise JobError(str(exc)) from exc
    working = resize_long_side(decoded.pixels, cfg.working_long_side)
    photo.width, photo.height = int(decoded.pixels.shape[1]), int(decoded.pixels.shape[0])
    photo.working_key = f"{photo.storage_prefix}working.jpg"
    photo.thumb_key = f"{photo.storage_prefix}thumb.webp"
    st.put(photo.working_key, encode_image(working, "jpg", 94), "image/jpeg")
    st.put(photo.thumb_key, encode_image(resize_long_side(working, cfg.thumbnail_long_side), "webp", 82), "image/webp")
    st.put(f"{photo.storage_prefix}preview.webp", encode_image(resize_long_side(working, cfg.preview_long_side), "webp", 88), "image/webp")

    router = get_router(preserve_article=True)
    bundle = analyze(working, router, progress)
    photo.mask_key = f"{photo.storage_prefix}analysis/mask.png"
    photo.labels_key = f"{photo.storage_prefix}analysis/labels.png"
    st.put(photo.mask_key, encode_mask(bundle.mask), "image/png")
    st.put(photo.labels_key, encode_mask(bundle.labels), "image/png")
    photo.analysis = jsonable(bundle.analysis.to_dict())
    photo.updated_at = datetime.now(UTC)
    db.flush()
    source_cache.drop(photo.id)

    settings = _settings_for(user, job.params)
    src = RenderSource(resize_long_side(working, 1600), bundle.mask, bundle.labels, bundle.analysis)
    outcome = enhance(src, settings, router.with_options(preserve_article=settings.preserve_article),
                      target_long_side=cfg.preview_long_side, progress=progress)
    version = save_version(
        db, photo, outcome.result, outcome.settings, kind="ai",
        auto_adjustments=outcome.auto_adjustments, needs_validation=outcome.needs_validation,
    )
    _record_calls(db, job, bundle.stages + outcome.stages)
    photo.status = "ready"
    photo.error = None
    return {"photo_id": str(photo.id), "version_id": str(version.id)}


# --- re-render a whole project with shared settings (+ consistency) ---------------------------


@handler("rerender")
def run_rerender(db: Session, job: Job, progress) -> dict:
    cfg = get_settings()
    project = db.get(Project, job.project_id)
    if project is None:
        raise JobError("Projet introuvable.")
    settings = EnhancementSettings(**job.params["settings"])
    photos = [p for p in project.photos if p.status == "ready" and p.analysis]
    if project.consistency_enabled and len(photos) >= 2:
        progress("consistency", "Harmonisation des photos", 0.05)
        analyses = [Analysis.from_dict(p.analysis) for p in photos]
        for p, c in zip(photos, harmonize(analyses), strict=True):
            p.analysis = {**p.analysis, "consistency": c}
            p.updated_at = datetime.now(UTC)
    else:
        for p in photos:
            if p.analysis and p.analysis.get("consistency"):
                p.analysis = {k: v for k, v in p.analysis.items() if k != "consistency"}
                p.updated_at = datetime.now(UTC)
    db.flush()
    versions = []
    for i, p in enumerate(photos):
        progress("render", f"Amélioration de la photo {i + 1}/{len(photos)}", 0.1 + 0.85 * i / max(1, len(photos)))
        source_cache.drop(p.id)
        src = load_source(p)
        router = get_router(preserve_article=settings.preserve_article)
        outcome = enhance(src, settings, router, target_long_side=cfg.preview_long_side,
                          use_consistency=bool(p.analysis.get("consistency")))
        v = save_version(db, p, outcome.result, outcome.settings, kind="edited",
                         auto_adjustments=outcome.auto_adjustments, needs_validation=outcome.needs_validation)
        _record_calls(db, job, outcome.stages)
        versions.append(str(v.id))
        db.commit()
    project.settings = settings.model_dump(mode="json")
    return {"versions": versions, "count": len(versions)}


# --- exports ---------------------------------------------------------------------------------------


def _export_one(db: Session, photo: Photo, version: PhotoVersion | None, fmt: str, quality: str, router) -> tuple[bytes, int, int]:
    cfg = get_settings()
    settings = EnhancementSettings(**(version.settings if version else {}))
    marketplace = get_marketplace(photo.project.marketplace if photo.project else "vinted")
    long_side = min(cfg.export_sizes[quality], marketplace.max_long_side if quality == "standard" else cfg.export_sizes[quality])
    src = load_source(photo, full=True)
    outcome = enhance(src, settings, router, target_long_side=long_side,
                      use_consistency=bool((photo.analysis or {}).get("consistency")), auto_guard=True)
    img = outcome.result.after
    data = encode_image(img, fmt, cfg.export_jpeg_quality[quality] if fmt in ("jpg", "jpeg", "webp") else 100)
    return data, int(img.shape[1]), int(img.shape[0])


@handler("export")
def run_export(db: Session, job: Job, progress) -> dict:
    photo = db.get(Photo, job.photo_id)
    if photo is None or photo.status != "ready":
        raise JobError("Photo non disponible.")
    fmt, quality = job.params["format"], job.params["quality"]
    version = None
    if job.params.get("version_id"):
        version = db.get(PhotoVersion, uuid.UUID(job.params["version_id"]))
        if version is None or version.photo_id != photo.id:
            raise JobError("Version introuvable.")
    version = version or current_version(photo)
    progress("render", "Rendu en pleine résolution", 0.2)
    router = get_router(preserve_article=(version.settings if version else {}).get("preserve_article", True))
    data, w, h = _export_one(db, photo, version, fmt, quality, router)
    progress("store", "Préparation du téléchargement", 0.9)
    marketplace = photo.project.marketplace if photo.project else "vinted"
    filename = export_filename(marketplace, photo.position, fmt)
    eid = uuid.uuid4()
    key = f"{user_prefix(photo.user_id)}exports/{eid}/{filename}"
    get_storage().put(key, data, MIME_BY_FORMAT[fmt])
    db.add(Export(id=eid, user_id=photo.user_id, photo_id=photo.id, version_id=version.id if version else None,
                  format=fmt, quality=quality, key=key, filename=filename, width=w, height=h, size_bytes=len(data)))
    if version is not None and version.kind != "final":
        final = PhotoVersion(
            photo_id=photo.id, kind="final", label="Version finale · exportée", settings=version.settings,
            metrics={**(version.metrics or {}), "export": {"format": fmt, "quality": quality, "width": w, "height": h}},
            after_key=version.after_key, before_key=version.before_key, thumb_key=version.thumb_key,
            width=version.width, height=version.height,
        )
        db.add(final)
        db.flush()
        photo.current_version_id = final.id
    return {"export_id": str(eid), "download_key": key, "filename": filename, "width": w, "height": h,
            "size_bytes": len(data), "format": fmt}


@handler("project_export")
def run_project_export(db: Session, job: Job, progress) -> dict:
    project = db.get(Project, job.project_id)
    if project is None:
        raise JobError("Projet introuvable.")
    fmt, quality = job.params["format"], job.params["quality"]
    photos = [p for p in project.photos if p.status == "ready"]
    if not photos:
        raise JobError("Aucune photo prête à exporter.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for i, p in enumerate(photos):
            progress("render", f"Export de la photo {i + 1}/{len(photos)}", 0.05 + 0.9 * i / len(photos))
            v = current_version(p)
            router = get_router(preserve_article=(v.settings if v else {}).get("preserve_article", True))
            data, _, _ = _export_one(db, p, v, fmt, quality, router)
            zf.writestr(export_filename(project.marketplace, p.position, fmt), data)
    filename = f"{get_marketplace(project.marketplace).slug}_ai_photos.zip"
    eid = uuid.uuid4()
    key = f"{user_prefix(project.user_id)}exports/{eid}/{filename}"
    payload = buf.getvalue()
    get_storage().put(key, payload, "application/zip")
    db.add(Export(id=eid, user_id=project.user_id, project_id=project.id, format=fmt, quality=quality, key=key,
                  filename=filename, size_bytes=len(payload)))
    return {"export_id": str(eid), "download_key": key, "filename": filename, "size_bytes": len(payload),
            "count": len(photos), "format": fmt}


# --- GDPR data export --------------------------------------------------------------------------------


@handler("gdpr_export")
def run_gdpr_export(db: Session, job: Job, progress) -> dict:
    user = db.get(User, job.user_id)
    if user is None:
        raise JobError("Compte introuvable.")
    st = get_storage()
    s = credits.summary(db, user)
    data = {
        "generated_at": datetime.now(UTC).isoformat(),
        "account": {
            "id": str(user.id), "email": user.email, "display_name": user.display_name, "created_at": user.created_at.isoformat(),
            "plan": user.plan_code, "retention_days": user.retention_days, "preferences": user.preferences,
        },
        "credits": {"allowance": s.allowance, "used": s.used, "remaining": s.remaining},
        "consents": [
            {"kind": c.kind, "granted": c.granted, "version": c.version, "at": c.created_at.isoformat()}
            for c in db.scalars(select(Consent).where(Consent.user_id == user.id))
        ],
        "subscriptions": [
            {"plan": x.plan_code, "status": x.status, "start": x.current_period_start.isoformat(), "end": x.current_period_end.isoformat()}
            for x in db.scalars(select(Subscription).where(Subscription.user_id == user.id))
        ],
        "credit_transactions": [
            {"delta": t.delta, "reason": t.reason, "at": t.created_at.isoformat()}
            for t in db.scalars(select(CreditTransaction).where(CreditTransaction.user_id == user.id))
        ],
        "projects": [],
    }
    buf = io.BytesIO()
    projects = list(db.scalars(select(Project).where(Project.user_id == user.id)))
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pi, project in enumerate(projects):
            progress("collect", "Rassemblement de tes données", 0.1 + 0.8 * pi / max(1, len(projects)))
            pdata = {"id": str(project.id), "name": project.name, "created_at": project.created_at.isoformat(), "photos": []}
            for photo in project.photos:
                folder = f"photos/{project.id}/{photo.id}/"
                try:
                    zf.writestr(folder + "original." + photo.original_key.rsplit(".", 1)[-1], st.get(photo.original_key))
                    v = current_version(photo)
                    if v:
                        zf.writestr(folder + "amelioree.webp", st.get(v.after_key))
                except FileNotFoundError:
                    pass
                pdata["photos"].append({
                    "id": str(photo.id), "filename": photo.original_filename, "created_at": photo.created_at.isoformat(),
                    "analysis": photo.analysis, "versions": [
                        {k: x[k] for k in ("id", "kind", "label", "created_at", "settings", "metrics")}
                        for x in (serialize_version(v) for v in photo.versions)
                    ],
                })
            data["projects"].append(pdata)
        zf.writestr("donnees.json", json.dumps(data, ensure_ascii=False, indent=2))
    filename = "mes-donnees-vinted-ai.zip"
    key = f"{user_prefix(user.id)}gdpr/{job.id}/{filename}"
    st.put(key, buf.getvalue(), "application/zip")
    return {"download_key": key, "filename": filename, "size_bytes": buf.tell()}


# --- benchmark ---------------------------------------------------------------------------------------


def _benchmark_failed(db: Session, job: Job, exc: Exception) -> None:
    run = db.get(BenchmarkRun, uuid.UUID(job.params["run_id"])) if job.params.get("run_id") else None
    if run is not None:
        run.status = "failed"
        run.finished_at = datetime.now(UTC)


@handler("benchmark", on_failure=_benchmark_failed)
def run_benchmark_job(db: Session, job: Job, progress) -> dict:
    from app.benchmark.runner import BenchmarkImage, run_benchmark, synthetic_set

    run = db.get(BenchmarkRun, uuid.UUID(job.params["run_id"]))
    run.status = "running"
    db.commit()
    images: list[BenchmarkImage] = []
    if run.image_source == "photos":
        st = get_storage()
        for pid in job.params.get("photo_ids", []):
            p = db.get(Photo, uuid.UUID(pid))
            if p is not None and p.user_id == run.created_by:
                images.append(BenchmarkImage(p.original_filename, decode_image(st.get(p.original_key)).pixels))
    else:
        images = synthetic_set(int(job.params.get("synthetic_count", 6)))
    settings = EnhancementSettings(**job.params.get("settings", {}))
    report = run_benchmark(images, run.profiles, get_providers(), settings=settings,
                           progress=lambda f: progress("benchmark", "Comparaison des modèles", f))
    run.results = jsonable(report["results"])
    run.summary = jsonable(report["summary"])
    run.image_count = len(images)
    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    return {"run_id": str(run.id)}
