"""Subscriptions: Stripe Checkout when configured, direct switch otherwise (dev/demo)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Plan, Subscription, User

log = logging.getLogger(__name__)


class BillingError(Exception):
    pass


def stripe_enabled() -> bool:
    cfg = get_settings()
    return bool(cfg.stripe_secret_key)


def activate_plan(db: Session, user: User, plan: Plan, *, provider: str = "manual", provider_ref: str | None = None,
                  period_end: datetime | None = None) -> Subscription:
    now = datetime.now(UTC)
    for sub in db.scalars(select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "active")):
        sub.status = "canceled"
    sub = Subscription(
        user_id=user.id, plan_code=plan.code, status="active", current_period_start=now,
        current_period_end=period_end or now + timedelta(days=30), provider=provider, provider_ref=provider_ref,
    )
    db.add(sub)
    user.plan_code = plan.code
    return sub


def start_checkout(db: Session, user: User, plan: Plan) -> dict:
    cfg = get_settings()
    if user.is_guest:
        raise BillingError("Crée un compte pour choisir une offre.")
    if plan.price_cents == 0:
        activate_plan(db, user, plan)
        return {"mode": "activated", "plan": plan.code}
    if not stripe_enabled():
        if cfg.is_production:
            raise BillingError("Le paiement n'est pas configuré.")
        activate_plan(db, user, plan)  # development: no payment provider, switch immediately
        return {"mode": "activated", "plan": plan.code}
    import stripe

    stripe.api_key = cfg.stripe_secret_key
    price_id = cfg.stripe_price_ids.get(plan.code)
    if not price_id:
        raise BillingError("Offre non disponible au paiement.")
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        customer_email=user.email,
        client_reference_id=str(user.id),
        metadata={"user_id": str(user.id), "plan_code": plan.code},
        success_url=f"{cfg.public_app_url}/app/billing?status=success",
        cancel_url=f"{cfg.public_app_url}/app/billing?status=cancel",
    )
    return {"mode": "redirect", "url": session.url}


def handle_webhook(db: Session, payload: bytes, signature: str | None) -> str:
    cfg = get_settings()
    if not stripe_enabled() or not cfg.stripe_webhook_secret:
        raise BillingError("webhook not configured")
    import stripe

    event = stripe.Webhook.construct_event(payload, signature or "", cfg.stripe_webhook_secret)
    obj = event["data"]["object"]
    if event["type"] == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        user = db.get(User, uuid.UUID(meta["user_id"])) if meta.get("user_id") else None
        plan = db.get(Plan, meta.get("plan_code")) if meta.get("plan_code") else None
        if user and plan:
            activate_plan(db, user, plan, provider="stripe", provider_ref=obj.get("subscription"))
    elif event["type"] in ("customer.subscription.deleted", "customer.subscription.paused"):
        sub = db.scalar(select(Subscription).where(Subscription.provider_ref == obj.get("id")))
        if sub:
            sub.status = "canceled"
            user = db.get(User, sub.user_id)
            if user:
                user.plan_code = "free"
    elif event["type"] == "invoice.paid":
        sub = db.scalar(select(Subscription).where(Subscription.provider_ref == obj.get("subscription")))
        if sub and obj.get("lines", {}).get("data"):
            period = obj["lines"]["data"][0].get("period", {})
            if period.get("start") and period.get("end"):
                sub.current_period_start = datetime.fromtimestamp(period["start"], UTC)
                sub.current_period_end = datetime.fromtimestamp(period["end"], UTC)
                sub.status = "active"
    return event["type"]
