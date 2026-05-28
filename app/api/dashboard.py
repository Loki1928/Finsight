"""Dashboard: total spend, total income, and category breakdowns."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import CanonicalEvent, User
from app.auth.dependencies import require_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    # ---- Spend side (debits, excluding internal transfers and CC bill payments) ----
    total_spend = (
        db.query(func.coalesce(func.sum(CanonicalEvent.amount), 0.0))
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.direction == "debit")
        .filter(CanonicalEvent.is_transfer == 0)
        .filter(CanonicalEvent.is_liability_payment == 0)
        .scalar()
    )
    by_category = (
        db.query(
            CanonicalEvent.category,
            func.sum(CanonicalEvent.amount).label("total"),
            func.count(CanonicalEvent.id).label("count"),
        )
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.direction == "debit")
        .filter(CanonicalEvent.is_transfer == 0)
        .filter(CanonicalEvent.is_liability_payment == 0)
        .group_by(CanonicalEvent.category)
        .order_by(func.sum(CanonicalEvent.amount).desc())
        .all()
    )

    # ---- Income side (credits, excluding internal transfers) ----
    # is_liability_payment doesn't apply to credits — a CC bill payment is
    # always a debit. is_transfer still applies (e.g. own-account moves
    # appearing as credits on the receiving side).
    total_income = (
        db.query(func.coalesce(func.sum(CanonicalEvent.amount), 0.0))
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.direction == "credit")
        .filter(CanonicalEvent.is_transfer == 0)
        .scalar()
    )
    income_by_category = (
        db.query(
            CanonicalEvent.category,
            func.sum(CanonicalEvent.amount).label("total"),
            func.count(CanonicalEvent.id).label("count"),
        )
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.direction == "credit")
        .filter(CanonicalEvent.is_transfer == 0)
        .group_by(CanonicalEvent.category)
        .order_by(func.sum(CanonicalEvent.amount).desc())
        .all()
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "total_spend": total_spend,
            "by_category": by_category,
            "total_income": total_income,
            "income_by_category": income_by_category,
            "user": user,
        },
    )