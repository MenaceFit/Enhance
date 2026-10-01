"""FastAPI application factory."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import set_session_cookie_raw
from app.api.routes import account, admin, auth, billing, files, photos
from app.core.config import get_settings
from app.core.db import Base, get_engine, session_scope
from app.imaging.image_io import HEIF_AVAILABLE
from app.imaging.settings import INTENSITY_LABELS, PRESETS
from app.marketplaces import MARKETPLACES
from app.models import Plan

log = logging.getLogger("app")


def seed(db) -> None:
    """Create missing plans from configuration (existing rows are never overwritten)."""
    cfg = get_settings()
    for p in cfg.plans:
        if db.get(Plan, p["code"]) is None:
            db.add(Plan(**p))


def _retention_loop(stop: threading.Event) -> None:  # pragma: no cover - background thread
    from app.services.privacy import purge_expired

    while not stop.wait(3600):
        try:
            with session_scope() as db:
                purge_expired(db)
        except Exception:
            log.exception("retention purge failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    logging.basicConfig(level=cfg.log_level)
    if cfg.auto_create_schema:
        Base.metadata.create_all(get_engine())
    with session_scope() as db:
        seed(db)
    stop = threading.Event()
    if cfg.job_backend == "inline" and cfg.environment != "test":
        threading.Thread(target=_retention_loop, args=(stop,), daemon=True, name="retention").start()
    yield
    stop.set()


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title=f"{cfg.app_name} API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if cfg.is_production else "/api/docs",
        openapi_url=None if cfg.is_production else "/api/openapi.json",
    )
    allowed_origins = set(cfg.cors_origins) | {cfg.public_app_url.rstrip("/")}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Requested-With"],
    )

    @app.middleware("http")
    async def security(request: Request, call_next):
        # CSRF defence in depth (cookies are SameSite=Lax): unsafe requests must come from our origin.
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.url.path.endswith("/billing/webhook"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") not in allowed_origins:
                return JSONResponse({"detail": "Origine non autorisée."}, status_code=403)
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        t0 = time.perf_counter()
        response = await call_next(request)
        new_session = getattr(request.state, "new_session", None)
        if new_session is not None and cfg.session_cookie_name not in response.headers.get("set-cookie", ""):
            set_session_cookie_raw(response, *new_session, guest=True)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if not request.url.path.startswith(f"{cfg.api_prefix}/files/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if cfg.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - t0) * 1000:.1f}"
        return response

    api = APIRouter(prefix=cfg.api_prefix)

    @api.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    @api.get("/config", tags=["meta"])
    def public_config():
        with session_scope() as db:
            plans = db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order)).all()
            plan_rows = [
                {"code": p.code, "name": p.name, "monthly_credits": p.monthly_credits, "price_cents": p.price_cents}
                for p in plans
            ]
        return {
            "app_name": cfg.app_name,
            "max_upload_mb": cfg.max_upload_mb,
            "max_photos_per_upload": cfg.max_photos_per_upload,
            "formats": ["jpg", "jpeg", "png", "webp"] + (["heic"] if HEIF_AVAILABLE else []),
            "export_formats": ["jpg", "png", "webp"],
            "export_qualities": {"standard": cfg.export_sizes["standard"], "high": cfg.export_sizes["high"], "max": cfg.export_sizes["max"]},
            "intensities": INTENSITY_LABELS,
            "presets": PRESETS,
            "marketplaces": [{"slug": m.slug, "name": m.name} for m in MARKETPLACES.values() if m.enabled],
            "plans": plan_rows,
            "guest_credits": cfg.guest_credits,
            "default_retention_days": cfg.default_retention_days,
        }

    for r in (auth.router, photos.router, billing.router, account.router, admin.router, files.router):
        api.include_router(r)
    app.include_router(api)
    return app


app = create_app()
