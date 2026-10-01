"""Admin analytics: usage, AI cost per model, performance, revenue."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CreditTransaction, Job, Plan, ProviderCall, Subscription, User


def _day(dt) -> str:
    return dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10]


def metrics(db: Session, days: int = 30) -> dict:
    now = datetime.now(UTC)
    since = now - timedelta(days=days)

    users_total = db.scalar(select(func.count()).select_from(User)) or 0
    registered = db.scalar(select(func.count()).select_from(User).where(User.is_guest.is_(False))) or 0
    new_users = db.scalar(select(func.count()).select_from(User).where(User.created_at >= since)) or 0

    jobs = list(
        db.execute(
            select(Job.type, Job.status, Job.created_at, Job.started_at, Job.finished_at, Job.cost_cents).where(Job.created_at >= since)
        )
    )
    enhance = [j for j in jobs if j.type == "enhance"]
    done = [j for j in enhance if j.status in ("succeeded", "failed")]
    ok = [j for j in enhance if j.status == "succeeded"]
    durations = sorted(
        (j.finished_at - j.started_at).total_seconds() * 1000 for j in ok if j.started_at and j.finished_at
    )

    per_day: dict[str, dict] = {}
    for i in range(days):
        d = (since + timedelta(days=i + 1)).date().isoformat()
        per_day[d] = {"date": d, "photos": 0, "failed": 0, "cost_cents": 0.0}
    for j in enhance:
        d = _day(j.created_at)
        if d in per_day:
            per_day[d]["photos" if j.status == "succeeded" else "failed"] += j.status in ("succeeded", "failed")
    calls = list(
        db.execute(
            select(ProviderCall.provider, ProviderCall.capability, ProviderCall.model, ProviderCall.duration_ms,
                   ProviderCall.cost_cents, ProviderCall.success, ProviderCall.created_at).where(ProviderCall.created_at >= since)
        )
    )
    for c in calls:
        d = _day(c.created_at)
        if d in per_day:
            per_day[d]["cost_cents"] = round(per_day[d]["cost_cents"] + (c.cost_cents or 0), 4)

    models: dict[tuple, dict] = defaultdict(lambda: {"calls": 0, "failures": 0, "cost_cents": 0.0, "duration_ms": 0.0})
    for c in calls:
        m = models[(c.provider, c.capability, c.model)]
        m["calls"] += 1
        m["failures"] += 0 if c.success else 1
        m["cost_cents"] += c.cost_cents or 0
        m["duration_ms"] += c.duration_ms or 0
    model_rows = [
        {
            "provider": p, "capability": cap, "model": model, "calls": v["calls"],
            "failure_rate": round(v["failures"] / v["calls"], 3) if v["calls"] else 0,
            "cost_cents": round(v["cost_cents"], 3), "avg_ms": round(v["duration_ms"] / v["calls"], 1) if v["calls"] else 0,
        }
        for (p, cap, model), v in sorted(models.items(), key=lambda kv: -kv[1]["calls"])
    ]

    credits_consumed = -(
        db.scalar(
            select(func.coalesce(func.sum(CreditTransaction.delta), 0)).where(
                CreditTransaction.reason.in_(("enhance", "refund")), CreditTransaction.created_at >= since
            )
        )
        or 0
    )

    active_subs = list(
        db.execute(
            select(Subscription.user_id, Plan.code, Plan.price_cents)
            .join(Plan, Plan.code == Subscription.plan_code)
            .where(Subscription.status == "active", Subscription.current_period_end > now, Plan.price_cents > 0)
        )
    )
    paying_users = {s.user_id for s in active_subs}
    mrr_cents = sum(s.price_cents for s in active_subs)
    plan_counts = dict(db.execute(select(User.plan_code, func.count()).where(User.is_guest.is_(False)).group_by(User.plan_code)).all())

    return {
        "period_days": days,
        "users": {"total": users_total, "registered": registered, "guests": users_total - registered, "new": new_users},
        "photos": {
            "processed": len(ok),
            "per_day": list(per_day.values()),
            "avg_per_day": round(len(ok) / days, 2),
        },
        "processing": {
            "avg_ms": round(sum(durations) / len(durations), 1) if durations else None,
            "p95_ms": round(durations[min(len(durations) - 1, int(len(durations) * 0.95))], 1) if durations else None,
            "error_rate": round(1 - len(ok) / len(done), 4) if done else 0.0,
        },
        "ai_cost": {
            "total_cents": round(sum(c.cost_cents or 0 for c in calls), 3),
            "per_photo_cents": round(sum(c.cost_cents or 0 for c in calls) / len(ok), 4) if ok else 0.0,
            "models": model_rows,
        },
        "credits": {"consumed": int(credits_consumed)},
        "revenue": {
            "mrr_cents": mrr_cents,
            "paying_users": len(paying_users),
            "conversion_free_to_paid": round(len(paying_users) / registered, 4) if registered else 0.0,
            "plans": plan_counts,
        },
    }
