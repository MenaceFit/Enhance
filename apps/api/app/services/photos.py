"""Photos: ingestion, render sources, versions, previews, serialisation."""

from __future__ import annotations

import hashlib
import io
import json
import threading
import uuid
from collections import OrderedDict
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.storage import get_storage, renders_prefix, user_prefix
from app.imaging.image_io import (
    ImageDecodeError,
    decode_mask,
    decode_rgb_fast,
    encode_image,
    resize_long_side,
    sniff_format,
)
from app.imaging.render import RenderResult, RenderSource
from app.imaging.settings import INTENSITY_LABELS, EnhancementSettings, explicit
from app.imaging.types import Analysis
from app.models import Photo, PhotoVersion, Project, User

PREVIEW_SOURCE_LONG_SIDE = 1600


class UploadRejected(ValueError):
    pass


# --- JSON helpers -------------------------------------------------------------------------


def jsonable(obj: Any) -> Any:
    """Recursively convert numpy / dataclass values into JSON-safe Python types."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


# --- ingestion ------------------------------------------------------------------------------


def retention_for(user: User) -> timedelta:
    cfg = get_settings()
    if user.is_guest:
        return timedelta(days=cfg.guest_retention_days)
    return timedelta(days=min(user.retention_days or cfg.default_retention_days, cfg.max_retention_days))


def probe_upload(filename: str, data: bytes) -> tuple[str, int, int]:
    """Cheap validation (header only): format and dimensions."""
    cfg = get_settings()
    if len(data) > cfg.max_upload_mb * 1024 * 1024:
        raise UploadRejected(f"{filename} : fichier trop lourd (max {cfg.max_upload_mb} Mo).")
    fmt = sniff_format(data)
    if fmt is None:
        raise UploadRejected(f"{filename} : format non pris en charge (JPG, PNG, WEBP ou HEIC).")
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
    except Exception as exc:
        raise UploadRejected(f"{filename} : image illisible.") from exc
    if min(w, h) < 64:
        raise UploadRejected(f"{filename} : image trop petite.")
    if w * h > 80_000_000:
        raise UploadRejected(f"{filename} : image trop grande.")
    return fmt, w, h


def default_project_name() -> str:
    months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    now = datetime.now(UTC)
    return f"Annonce du {now.day} {months[now.month - 1]}"


def create_photo(db: Session, user: User, project: Project, position: int, filename: str, data: bytes) -> Photo:
    fmt, w, h = probe_upload(filename, data)
    pid = uuid.uuid4()
    prefix = f"{user_prefix(user.id)}photos/{pid}/"
    ext = {"jpeg": "jpg"}.get(fmt, fmt)
    key = f"{prefix}original.{ext}"
    st = get_storage()
    st.put(key, data)
    thumb_key = _quick_thumbnail(st, prefix, data)
    photo = Photo(
        id=pid,
        user_id=user.id,
        project_id=project.id,
        position=position,
        original_filename=filename[:255] or f"photo.{ext}",
        source_format=fmt,
        size_bytes=len(data),
        width=w,
        height=h,
        status="queued",
        storage_prefix=prefix,
        original_key=key,
        thumb_key=thumb_key,
        expires_at=datetime.now(UTC) + retention_for(user),
    )
    db.add(photo)
    return photo


def _quick_thumbnail(st, prefix: str, data: bytes) -> str | None:
    """Small preview stored at upload so the processing screen shows the photo at once.

    JPEG decoding uses Pillow's draft mode (DCT scaling), so this costs a few ms.
    """
    from PIL import ImageOps

    try:
        with Image.open(io.BytesIO(data)) as im:
            im.draft("RGB", (640, 640))
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((get_settings().thumbnail_long_side,) * 2)
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=78)
        key = f"{prefix}thumb.webp"
        st.put(key, buf.getvalue(), "image/webp")
        return key
    except Exception:
        return None


# --- render sources (cached for snappy editor previews) ------------------------------------


class _SourceCache:
    def __init__(self, size: int = 24):
        self.size = size
        self._data: OrderedDict[tuple, RenderSource] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            v = self._data.get(key)
            if v is not None:
                self._data.move_to_end(key)
            return v

    def put(self, key, value):
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)

    def drop(self, photo_id) -> None:
        with self._lock:
            for k in [k for k in self._data if k[0] == photo_id]:
                del self._data[k]


source_cache = _SourceCache()


def load_source(photo: Photo, *, full: bool = False) -> RenderSource:
    if not (photo.working_key and photo.mask_key and photo.labels_key and photo.analysis):
        raise ImageDecodeError("photo not analysed yet")
    key = (photo.id, "full" if full else "preview", photo.updated_at.isoformat() if photo.updated_at else "")
    hit = source_cache.get(key)
    if hit is not None:
        return hit
    st = get_storage()
    img = decode_rgb_fast(st.get(photo.working_key))
    if not full:
        img = resize_long_side(img, PREVIEW_SOURCE_LONG_SIDE)
    src = RenderSource(
        image=img,
        mask=decode_mask(st.get(photo.mask_key)),
        labels=decode_mask(st.get(photo.labels_key)),
        analysis=Analysis.from_dict(photo.analysis),
    )
    if not full:
        source_cache.put(key, src)
    return src


# --- versions & previews -------------------------------------------------------------------


def metrics_from(result: RenderResult, photo: Photo, *, auto_adjustments=None, needs_validation=False) -> dict:
    quality_before = (photo.analysis or {}).get("quality", {}).get("score")
    return jsonable({
        "fidelity": result.fidelity,
        "structure": result.structure,
        "quality": result.quality,
        "quality_before": quality_before,
        "applied": result.applied,
        "warnings": result.warnings,
        "geometry": result.geometry,
        "upscale_factor": result.upscale_factor,
        "removed_specks": len(result.removed_specks),
        "auto_adjustments": auto_adjustments or [],
        "needs_validation": needs_validation,
        "capped": result.settings.capped,
        "timings": result.timings,
    })


def _store_render(prefix: str, result: RenderResult) -> tuple[str, str, str]:
    st = get_storage()
    after_key, before_key, thumb_key = f"{prefix}after.webp", f"{prefix}before.webp", f"{prefix}thumb.webp"
    st.put(after_key, encode_image(result.after, "webp", 90), "image/webp")
    st.put(before_key, encode_image(result.before, "webp", 88), "image/webp")
    st.put(thumb_key, encode_image(resize_long_side(result.after, get_settings().thumbnail_long_side), "webp", 82), "image/webp")
    return after_key, before_key, thumb_key


def save_version(
    db: Session,
    photo: Photo,
    result: RenderResult,
    settings: EnhancementSettings,
    *,
    kind: str,
    label: str | None = None,
    auto_adjustments=None,
    needs_validation: bool = False,
    make_current: bool = True,
) -> PhotoVersion:
    vid = uuid.uuid4()
    after_key, before_key, thumb_key = _store_render(f"{photo.storage_prefix}versions/{vid}/", result)
    v = PhotoVersion(
        id=vid,
        photo_id=photo.id,
        kind=kind,
        label=label or default_label(kind, settings),
        settings=jsonable(explicit(settings).model_dump(mode="json")),
        metrics=metrics_from(result, photo, auto_adjustments=auto_adjustments, needs_validation=needs_validation),
        after_key=after_key,
        before_key=before_key,
        thumb_key=thumb_key,
        width=int(result.after.shape[1]),
        height=int(result.after.shape[0]),
    )
    db.add(v)
    if make_current:
        photo.current_version_id = vid
    return v


def default_label(kind: str, settings: EnhancementSettings) -> str:
    base = {"ai": "Version IA", "edited": "Version modifiée", "final": "Version finale"}.get(kind, "Version")
    return f"{base} · {INTENSITY_LABELS[settings.intensity]}"


def preview_render(photo: Photo, settings: EnhancementSettings) -> dict:
    """Render at preview size, cached by settings hash in storage."""
    from app.imaging.pipeline import enhance
    from app.providers.registry import get_router

    cfg = get_settings()
    st = get_storage()
    consistency = (photo.analysis or {}).get("consistency")
    variant = hashlib.sha1(json.dumps(consistency, sort_keys=True).encode()).hexdigest()[:8] if consistency else "solo"
    prefix = f"{renders_prefix(photo.user_id, photo.id)}{settings.cache_key()}-{variant}/"
    meta_key = f"{prefix}metrics.json"
    if st.exists(meta_key):
        payload = json.loads(st.get(meta_key))
    else:
        src = load_source(photo)
        project_consistency = bool((photo.analysis or {}).get("consistency"))
        outcome = enhance(
            src, settings, get_router(preserve_article=settings.preserve_article),
            target_long_side=cfg.preview_long_side, use_consistency=project_consistency,
        )
        r = outcome.result
        after_key, before_key, thumb_key = _store_render(prefix, r)
        payload = {
            "after_key": after_key,
            "before_key": before_key,
            "thumb_key": thumb_key,
            "width": int(r.after.shape[1]),
            "height": int(r.after.shape[0]),
            "settings": jsonable(explicit(outcome.settings).model_dump(mode="json")),
            "metrics": metrics_from(r, photo, auto_adjustments=outcome.auto_adjustments, needs_validation=outcome.needs_validation),
        }
        st.put(meta_key, json.dumps(payload).encode(), "application/json")
    return {
        "after_url": st.signed_url(payload["after_key"]),
        "before_url": st.signed_url(payload["before_key"]),
        "width": payload["width"],
        "height": payload["height"],
        "settings": payload["settings"],
        "metrics": payload["metrics"],
        "cache_prefix": prefix,
    }


def save_preview_as_version(db: Session, photo: Photo, settings: EnhancementSettings, *, kind: str, label: str | None) -> PhotoVersion:
    preview = preview_render(photo, settings)
    st = get_storage()
    vid = uuid.uuid4()
    vprefix = f"{photo.storage_prefix}versions/{vid}/"
    src_prefix = preview["cache_prefix"]
    for name in ("after.webp", "before.webp", "thumb.webp"):
        st.copy(f"{src_prefix}{name}", f"{vprefix}{name}")
    v = PhotoVersion(
        id=vid,
        photo_id=photo.id,
        kind=kind,
        label=label or default_label(kind, settings),
        settings=preview["settings"],
        metrics=preview["metrics"],
        after_key=f"{vprefix}after.webp",
        before_key=f"{vprefix}before.webp",
        thumb_key=f"{vprefix}thumb.webp",
        width=preview["width"],
        height=preview["height"],
    )
    db.add(v)
    photo.current_version_id = vid
    return v


# --- serialisation ----------------------------------------------------------------------------


def current_version(photo: Photo) -> PhotoVersion | None:
    if photo.current_version_id is None:
        return None
    return next((v for v in photo.versions if v.id == photo.current_version_id), None)


def serialize_version(v: PhotoVersion) -> dict:
    st = get_storage()
    return {
        "id": str(v.id),
        "kind": v.kind,
        "label": v.label,
        "created_at": v.created_at.isoformat(),
        "settings": v.settings,
        "metrics": v.metrics,
        "width": v.width,
        "height": v.height,
        "after_url": st.signed_url(v.after_key),
        "before_url": st.signed_url(v.before_key),
        "thumb_url": st.signed_url(v.thumb_key),
    }


def checklist(photo: Photo, v: PhotoVersion | None) -> dict:
    applied = (v.metrics or {}).get("applied", {}) if v else {}
    return {
        "cleaned": bool(applied.get("cleaned")),
        "colors": bool(applied.get("colors") or applied.get("light")),
        "framing": bool(applied.get("framing")),
        "background": bool(applied.get("background")),
    }


def serialize_photo(photo: Photo, *, detail: bool = False) -> dict:
    st = get_storage()
    v = current_version(photo)
    analysis = photo.analysis or {}
    data = {
        "id": str(photo.id),
        "project_id": str(photo.project_id),
        "position": photo.position,
        "filename": photo.original_filename,
        "status": photo.status,
        "error": photo.error,
        "width": photo.width,
        "height": photo.height,
        "is_favorite": photo.is_favorite,
        "created_at": photo.created_at.isoformat(),
        "expires_at": photo.expires_at.isoformat() if photo.expires_at else None,
        "thumb_url": st.signed_url(v.thumb_key) if v else (st.signed_url(photo.thumb_key) if photo.thumb_key else None),
        "original_thumb_url": st.signed_url(photo.thumb_key) if photo.thumb_key else None,
        "garment": (analysis.get("clothing") or {}).get("label"),
        "quality_before": (analysis.get("quality") or {}).get("score"),
        "quality_after": ((v.metrics or {}).get("quality") or {}).get("score") if v else None,
        "fidelity": ((v.metrics or {}).get("fidelity") or {}).get("score") if v else None,
        "defects_count": len([d for d in analysis.get("defects", []) if d.get("kind") != "speck"]),
        "checklist": checklist(photo, v),
    }
    if detail:
        data.update({
            "original_preview_url": st.signed_url(f"{photo.storage_prefix}preview.webp") if photo.working_key else None,
            "analysis": analysis,
            "defect_state": photo.defect_state or {},
            "current_version": serialize_version(v) if v else None,
            "versions": [serialize_version(x) for x in reversed(photo.versions)],
        })
    return data


def serialize_project(project: Project, *, with_photos: bool = True) -> dict:
    photos = list(project.photos)
    data = {
        "id": str(project.id),
        "name": project.name,
        "marketplace": project.marketplace,
        "consistency_enabled": project.consistency_enabled,
        "settings": project.settings or {},
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "photo_count": len(photos),
        "ready_count": sum(p.status == "ready" for p in photos),
        "cover_url": next((serialize_photo(p)["thumb_url"] for p in photos if p.status == "ready"), None),
    }
    if with_photos:
        data["photos"] = [serialize_photo(p) for p in photos]
    return data
