"""Dashboard: total spend and spend by category."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import CanonicalEvent

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    total_spend = (
        db.query(func.coalesce(func.sum(CanonicalEvent.amount), 0.0))
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
        .filter(CanonicalEvent.direction == "debit")
        .filter(CanonicalEvent.is_transfer == 0)
        .filter(CanonicalEvent.is_liability_payment == 0)
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
        },
    )
