"""Asynchronous jobs: creation, dispatch, execution, progress.

UPLOAD → CREATE JOB → QUEUE → AI PROCESSING → QUALITY CHECK → STORE RESULT →
NOTIFY FRONTEND (polling ``GET /jobs``).

Backends:
* ``celery`` — Redis broker, separate worker processes (production);
* ``inline`` — a thread pool inside the API process (development, small installs);
* ``sync``   — run immediately in the caller (tests).
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import Job

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, str, float], None]
Handler = Callable[[Session, Job, ProgressFn], dict | None]
FailureHook = Callable[[Session, Job, Exception], None]

_handlers: dict[str, Handler] = {}
_failure_hooks: dict[str, FailureHook] = {}


class JobError(Exception):
    """Expected failure with a user-facing message."""


def handler(job_type: str, on_failure: FailureHook | None = None):
    def deco(fn: Handler) -> Handler:
        _handlers[job_type] = fn
        if on_failure:
            _failure_hooks[job_type] = on_failure
        return fn

    return deco


def create_job(
    db: Session,
    job_type: str,
    *,
    user_id: uuid.UUID | None,
    params: dict | None = None,
    photo_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> Job:
    job = Job(
        type=job_type, user_id=user_id, params=params or {}, photo_id=photo_id, project_id=project_id,
        status="queued", progress=0.0, stage="queued", stage_label="En attente…",
    )
    db.add(job)
    return job


@lru_cache
def _pool() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=get_settings().inline_workers, thread_name_prefix="job")


def enqueue(job_ids: list[uuid.UUID]) -> None:
    """Dispatch jobs. Call only after the creating transaction is committed."""
    backend = get_settings().job_backend
    for jid in job_ids:
        if backend == "celery":
            from app.workers.tasks import run_job

            run_job.delay(str(jid))
        elif backend == "sync":
            execute(jid)
        else:
            _pool().submit(execute, jid)


def execute(job_id: uuid.UUID | str) -> None:
    _load_handlers()
    jid = uuid.UUID(str(job_id))
    db = get_sessionmaker()()
    try:
        job = db.get(Job, jid)
        if job is None or job.status not in ("queued", "running"):
            return
        fn = _handlers.get(job.type)
        if fn is None:
            raise RuntimeError(f"no handler for job type {job.type}")
        job.status = "running"
        job.started_at = datetime.now(UTC)
        db.commit()

        last = {"t": 0.0, "stage": None}
        lock = threading.Lock()

        def progress(stage: str, label: str, fraction: float) -> None:
            now = time.monotonic()
            with lock:
                if stage == last["stage"] and now - last["t"] < 0.25:
                    return
                last.update(t=now, stage=stage)
            job.stage, job.stage_label = stage, label
            job.progress = round(max(job.progress or 0.0, min(0.99, fraction)), 3)
            db.commit()

        t0 = time.perf_counter()
        result = fn(db, job, progress) or {}
        job.result = {**result, "duration_ms": round((time.perf_counter() - t0) * 1000, 1)}
        job.status = "succeeded"
        job.progress = 1.0
        job.stage, job.stage_label = "done", "Terminé"
        job.finished_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - job failures are recorded, never raised to the pool
        db.rollback()
        job = db.get(Job, jid)
        if job is None:
            return
        user_message = str(exc) if isinstance(exc, JobError) else "Une erreur est survenue pendant le traitement."
        log.error("job %s (%s) failed: %s", jid, job.type, "".join(traceback.format_exception(exc))[-2000:])
        job.status = "failed"
        job.error = user_message
        job.stage, job.stage_label = "failed", user_message
        job.finished_at = datetime.now(UTC)
        hook = _failure_hooks.get(job.type)
        if hook:
            try:
                hook(db, job, exc)
            except Exception:  # pragma: no cover - defensive
                log.exception("failure hook crashed for job %s", jid)
        db.commit()
    finally:
        db.close()


def _load_handlers() -> None:
    if not _handlers:
        import app.services.processing  # noqa: F401 - registers handlers


def serialize_job(job: Job) -> dict:
    data = {
        "id": str(job.id),
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "stage_label": job.stage_label,
        "error": job.error,
        "photo_id": str(job.photo_id) if job.photo_id else None,
        "project_id": str(job.project_id) if job.project_id else None,
        "created_at": job.created_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "result": job.result or None,
    }
    if job.status == "succeeded" and job.result and job.result.get("download_key"):
        from app.core.storage import get_storage

        data["result"] = {
            **{k: v for k, v in job.result.items() if k != "download_key"},
            "download_url": get_storage().signed_url(job.result["download_key"], download_name=job.result.get("filename")),
        }
    return data
