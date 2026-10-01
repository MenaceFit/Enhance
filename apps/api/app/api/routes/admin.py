"""Admin: analytics, AI providers & costs, plans, model benchmarks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.routes.billing import serialize_plan
from app.benchmark.runner import PRESET_PROFILES
from app.core.config import get_settings
from app.core.db import get_db
from app.imaging.settings import EnhancementSettings
from app.models import BenchmarkRun, Plan, User
from app.providers.registry import get_providers, parse_routing
from app.services import analytics, credits
from app.services.jobs import create_job, enqueue, serialize_job

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/metrics")
def get_metrics(days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db)):
    return analytics.metrics(db, days)


@router.get("/providers")
def providers():
    return {
        "providers": [p.describe() for p in get_providers().values()],
        "routing": parse_routing(get_settings().ai_routing),
        "preset_profiles": PRESET_PROFILES,
    }


class PlanPatch(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    monthly_credits: int | None = Field(default=None, ge=0, le=1_000_000)
    price_cents: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


@router.get("/plans")
def list_plans(db: Session = Depends(get_db)):
    return {"plans": [serialize_plan(p) | {"is_active": p.is_active} for p in db.scalars(select(Plan).order_by(Plan.sort_order))]}


@router.patch("/plans/{code}")
def patch_plan(code: str, body: PlanPatch, db: Session = Depends(get_db)):
    plan = db.get(Plan, code)
    if plan is None:
        raise HTTPException(404, "Offre introuvable.")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(plan, field, value)
    db.commit()
    return serialize_plan(plan) | {"is_active": plan.is_active}


class GrantIn(BaseModel):
    amount: int = Field(ge=1, le=10_000)


@router.post("/users/{user_id}/credits")
def grant_credits(user_id: str, body: GrantIn, db: Session = Depends(get_db)):
    user = db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(404, "Utilisateur introuvable.")
    credits.grant(db, user, body.amount)
    db.commit()
    return {"remaining": credits.summary(db, user).remaining}


class BenchmarkIn(BaseModel):
    profiles: list[str] = Field(default_factory=lambda: ["local"], min_length=1, max_length=6)
    custom_profiles: dict[str, dict[str, str]] = Field(default_factory=dict)
    synthetic_count: int = Field(default=6, ge=1, le=40)
    photo_ids: list[str] = Field(default_factory=list, max_length=40)
    settings: EnhancementSettings = Field(default_factory=EnhancementSettings)


def serialize_run(run: BenchmarkRun, *, with_results: bool = False) -> dict:
    data = {
        "id": str(run.id), "status": run.status, "profiles": run.profiles, "image_source": run.image_source,
        "image_count": run.image_count, "summary": run.summary, "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None, "job_id": str(run.job_id) if run.job_id else None,
    }
    if with_results:
        data["results"] = run.results
    return data


@router.post("/benchmarks", status_code=202)
def start_benchmark(body: BenchmarkIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    profiles: dict[str, dict[str, str]] = {}
    for name in body.profiles:
        if name not in PRESET_PROFILES:
            raise HTTPException(422, f"Profil inconnu : {name}")
        profiles[name] = PRESET_PROFILES[name]
    profiles.update(body.custom_profiles)
    run = BenchmarkRun(created_by=admin.id, profiles=profiles, image_source="photos" if body.photo_ids else "synthetic")
    db.add(run)
    db.flush()
    job = create_job(db, "benchmark", user_id=admin.id, params={
        "run_id": str(run.id), "synthetic_count": body.synthetic_count, "photo_ids": body.photo_ids,
        "settings": body.settings.model_dump(mode="json"),
    })
    db.flush()
    run.job_id = job.id
    db.commit()
    enqueue([job.id])
    return {"run": serialize_run(run), "job": serialize_job(job)}


@router.get("/benchmarks")
def list_benchmarks(db: Session = Depends(get_db)):
    runs = db.scalars(select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).limit(50)).all()
    return {"runs": [serialize_run(r) for r in runs]}


@router.get("/benchmarks/{run_id}")
def get_benchmark(run_id: str, db: Session = Depends(get_db)):
    run = db.get(BenchmarkRun, uuid.UUID(run_id))
    if run is None:
        raise HTTPException(404, "Benchmark introuvable.")
    return serialize_run(run, with_results=True)
