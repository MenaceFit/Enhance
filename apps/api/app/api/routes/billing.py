from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_user
from app.core.db import get_db
from app.models import CreditTransaction, Plan, User
from app.services import billing, credits

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutIn(BaseModel):
    plan_code: str


def serialize_plan(p: Plan) -> dict:
    return {
        "code": p.code, "name": p.name, "monthly_credits": p.monthly_credits, "price_cents": p.price_cents,
        "currency": p.currency, "features": p.features or {},
    }


@router.get("/plans")
def plans(db: Session = Depends(get_db)):
    rows = db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order)).all()
    return {"plans": [serialize_plan(p) for p in rows], "payments_enabled": billing.stripe_enabled()}


@router.get("")
def summary(user: User = Depends(require_user), db: Session = Depends(get_db)):
    s = credits.summary(db, user)
    history = db.scalars(
        select(CreditTransaction).where(CreditTransaction.user_id == user.id).order_by(CreditTransaction.created_at.desc()).limit(50)
    ).all()
    return {
        "plan_code": s.plan_code, "plan_name": s.plan_name, "allowance": s.allowance, "used": s.used,
        "remaining": s.remaining, "period_start": s.period_start.isoformat(), "period_end": s.period_end.isoformat(),
        "history": [{"delta": t.delta, "reason": t.reason, "at": t.created_at.isoformat()} for t in history],
        "payments_enabled": billing.stripe_enabled(),
    }


@router.post("/checkout")
def checkout(body: CheckoutIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    plan = db.get(Plan, body.plan_code)
    if plan is None or not plan.is_active:
        raise HTTPException(404, "Offre introuvable.")
    try:
        result = billing.start_checkout(db, user, plan)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return result


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    try:
        event = billing.handle_webhook(db, payload, request.headers.get("stripe-signature"))
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # invalid signature / payload
        raise HTTPException(400, "Invalid webhook") from exc
    db.commit()
    return {"received": event}
