from __future__ import annotations

from app.core.db import session_scope
from app.workers.celery_app import celery


@celery.task(name="app.workers.tasks.run_job")
def run_job(job_id: str) -> None:
    from app.services.jobs import execute

    execute(job_id)


@celery.task(name="app.workers.tasks.purge")
def purge() -> dict:
    from app.services.privacy import purge_expired

    with session_scope() as db:
        return purge_expired(db)
