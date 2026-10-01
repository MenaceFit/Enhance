"""Celery application (Redis broker). Start with:

    celery -A app.workers.celery_app worker --loglevel=INFO --concurrency=4
    celery -A app.workers.celery_app beat --loglevel=INFO
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

cfg = get_settings()

celery = Celery("vinted_ai", broker=cfg.redis_url, include=["app.workers.tasks"])
celery.conf.update(
    task_acks_late=True,  # a crashed worker hands the photo to another one
    worker_prefetch_multiplier=1,  # long CPU tasks: no hoarding
    task_reject_on_worker_lost=True,
    task_default_queue="photos",
    task_time_limit=600,
    task_soft_time_limit=540,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "retention-purge": {"task": "app.workers.tasks.purge", "schedule": 3600.0},
    },
)

app = celery
