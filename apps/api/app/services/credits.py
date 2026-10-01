"""Credits: monthly allowance per plan + an append-only ledger.

balance = allowance(plan) + Σ ledger deltas in the current period

Consumption is a negative entry (``enhance``), failures are refunded with a
positive ``refund`` entry, admins can grant ``bonus`` credits. Plan limits live
in the ``plans`` table so they can be changed without a deploy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CreditTransaction, Plan, Subscription, User


class InsufficientCredits(Exception):
    def __init__(self, needed: int, remaining: int):
        super().__init__(f"needed {needed}, remaining {remaining}")
        self.needed = needed
        self.remaining = remaining


@dataclass
class CreditSummary:
    plan_code: str
    plan_name: str
    allowance: int
    used: int
    remaining: int
    period_start: datetime
    period_end: datetime


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def active_subscription(db: Session, user: User) -> Subscription | None:
    now = datetime.now(UTC)
    return db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.status == "active", Subscription.current_period_end > now)
        .order_by(Subscription.created_at.desc())
    )


def current_period(db: Session, user: User) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if user.is_guest:
        created = user.created_at if user.created_at.tzinfo else user.created_at.replace(tzinfo=UTC)
        return created, created.replace(year=created.year + 1)
    sub = active_subscription(db, user)
    if sub:
        start = sub.current_period_start if sub.current_period_start.tzinfo else sub.current_period_start.replace(tzinfo=UTC)
        end = sub.current_period_end if sub.current_period_end.tzinfo else sub.current_period_end.replace(tzinfo=UTC)
        return start, end
    return _month_bounds(now)


def plan_for(db: Session, user: User) -> tuple[str, str, int]:
    cfg = get_settings()
    if user.is_guest:
        return "guest", "Invité", cfg.guest_credits
    plan = db.get(Plan, user.plan_code) or db.get(Plan, "free")
    if plan is None:
        return "free", "Free", 5
    return plan.code, plan.name, plan.monthly_credits


def summary(db: Session, user: User) -> CreditSummary:
    start, end = current_period(db, user)
    code, name, allowance = plan_for(db, user)
    total_delta = db.scalar(
        select(func.coalesce(func.sum(CreditTransaction.delta), 0)).where(
            CreditTransaction.user_id == user.id,
            CreditTransaction.created_at >= start,
            CreditTransaction.created_at < end,
        )
    )
    used = db.scalar(
        select(func.coalesce(func.sum(CreditTransaction.delta), 0)).where(
            CreditTransaction.user_id == user.id,
            CreditTransaction.reason.in_(("enhance", "refund")),
            CreditTransaction.created_at >= start,
            CreditTransaction.created_at < end,
        )
    )
    remaining = max(0, allowance + int(total_delta or 0))
    return CreditSummary(code, name, allowance, max(0, -int(used or 0)), remaining, start, end)


def consume(db: Session, user: User, amount: int, *, photo_ids: list[uuid.UUID] | None = None) -> list[CreditTransaction]:
    """Reserve credits atomically (row lock on the user in PostgreSQL)."""
    if amount <= 0:
        return []
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    s = summary(db, user)
    if s.remaining < amount:
        raise InsufficientCredits(amount, s.remaining)
    per = get_settings().credit_cost_enhance
    entries = []
    ids = photo_ids or [None] * (amount // max(per, 1))
    for pid in ids:
        e = CreditTransaction(user_id=user.id, delta=-per, reason="enhance", photo_id=pid)
        db.add(e)
        entries.append(e)
    return entries


def refund(db: Session, user_id: uuid.UUID, photo_id: uuid.UUID | None, job_id: uuid.UUID | None = None) -> None:
    already = db.scalar(
        select(func.count()).select_from(CreditTransaction).where(
            CreditTransaction.user_id == user_id, CreditTransaction.reason == "refund", CreditTransaction.photo_id == photo_id
        )
    )
    if photo_id is not None and already:
        return
    db.add(
        CreditTransaction(
            user_id=user_id, delta=get_settings().credit_cost_enhance, reason="refund", photo_id=photo_id, job_id=job_id
        )
    )


def grant(db: Session, user: User, amount: int) -> None:
    db.add(CreditTransaction(user_id=user.id, delta=amount, reason="bonus"))
