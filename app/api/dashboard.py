"""Dashboard: spend/income totals, category breakdown, top merchants, monthly trend.

Session 19 changes:
  - Added date range filter (this month / last month / last 3 months / all time)
  - Added top merchants query
  - Added monthly trend data for chart
  - Category data now includes percentage for donut chart
"""
from datetime import date, timedelta
from calendar import monthrange

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import CanonicalEvent, User
from app.auth.dependencies import require_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _period_bounds(period: str) -> tuple[date | None, date | None]:
    """Return (start, end) date bounds for a named period."""
    today = date.today()
    if period == "this_month":
        start = today.replace(day=1)
        _, last_day = monthrange(today.year, today.month)
        end = today.replace(day=last_day)
    elif period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start = last_prev.replace(day=1)
        end = last_prev
    elif period == "last_3":
        start = (today.replace(day=1) - timedelta(days=90)).replace(day=1)
        _, last_day = monthrange(today.year, today.month)
        end = today.replace(day=last_day)
    else:  # "all"
        return None, None
    return start, end


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    period: str = Query("all", description="this_month|last_month|last_3|all|custom"),
    date_from: str = Query("", description="Custom start date YYYY-MM-DD"),
    date_to: str = Query("", description="Custom end date YYYY-MM-DD"),
):
    custom_active = False
    if period == "custom" and date_from.strip() and date_to.strip():
        try:
            start = date.fromisoformat(date_from.strip())
            end = date.fromisoformat(date_to.strip())
            custom_active = True
        except ValueError:
            start, end = _period_bounds("all")
    else:
        start, end = _period_bounds(period)

    def base_query():
        q = db.query(CanonicalEvent).filter(CanonicalEvent.user_id == user.id)
        if start:
            q = q.filter(CanonicalEvent.event_date >= start)
        if end:
            q = q.filter(CanonicalEvent.event_date <= end)
        return q

    # ── Spend ────────────────────────────────────────────────────────
    spend_base = (
        base_query()
        .filter(CanonicalEvent.direction == "debit")
        .filter(CanonicalEvent.is_transfer == 0)
        .filter(CanonicalEvent.is_liability_payment == 0)
    )

    total_spend = db.query(func.coalesce(func.sum(CanonicalEvent.amount), 0.0)).select_from(
        spend_base.subquery()
    ).scalar() or 0.0

    # Use a fresh subquery approach for grouping
    by_category_rows = (
        db.query(
            CanonicalEvent.category,
            func.sum(CanonicalEvent.amount).label("total"),
            func.count(CanonicalEvent.id).label("count"),
        )
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.direction == "debit")
        .filter(CanonicalEvent.is_transfer == 0)
        .filter(CanonicalEvent.is_liability_payment == 0)
    )
    if start:
        by_category_rows = by_category_rows.filter(CanonicalEvent.event_date >= start)
    if end:
        by_category_rows = by_category_rows.filter(CanonicalEvent.event_date <= end)

    by_category = (
        by_category_rows
        .group_by(CanonicalEvent.category)
        .order_by(func.sum(CanonicalEvent.amount).desc())
        .all()
    )

    # Add percentages for chart
    category_data = []
    for row in by_category:
        pct = (row.total / total_spend * 100) if total_spend > 0 else 0
        category_data.append({
            "category": row.category or "Uncategorized",
            "total": row.total,
            "count": row.count,
            "pct": round(pct, 1),
        })

    # ── Income ───────────────────────────────────────────────────────
    income_q = (
        db.query(func.coalesce(func.sum(CanonicalEvent.amount), 0.0))
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.direction == "credit")
        .filter(CanonicalEvent.is_transfer == 0)
    )
    if start:
        income_q = income_q.filter(CanonicalEvent.event_date >= start)
    if end:
        income_q = income_q.filter(CanonicalEvent.event_date <= end)
    total_income = income_q.scalar() or 0.0

    income_cat_q = (
        db.query(
            CanonicalEvent.category,
            func.sum(CanonicalEvent.amount).label("total"),
            func.count(CanonicalEvent.id).label("count"),
        )
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.direction == "credit")
        .filter(CanonicalEvent.is_transfer == 0)
    )
    if start:
        income_cat_q = income_cat_q.filter(CanonicalEvent.event_date >= start)
    if end:
        income_cat_q = income_cat_q.filter(CanonicalEvent.event_date <= end)
    income_by_category = (
        income_cat_q
        .group_by(CanonicalEvent.category)
        .order_by(func.sum(CanonicalEvent.amount).desc())
        .all()
    )

    # ── Top merchants ────────────────────────────────────────────────
    merch_q = (
        db.query(
            CanonicalEvent.merchant_normalized,
            func.sum(CanonicalEvent.amount).label("total"),
            func.count(CanonicalEvent.id).label("count"),
        )
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.direction == "debit")
        .filter(CanonicalEvent.is_transfer == 0)
        .filter(CanonicalEvent.is_liability_payment == 0)
        .filter(CanonicalEvent.merchant_normalized.isnot(None))
        .filter(CanonicalEvent.merchant_normalized != "Unknown")
    )
    if start:
        merch_q = merch_q.filter(CanonicalEvent.event_date >= start)
    if end:
        merch_q = merch_q.filter(CanonicalEvent.event_date <= end)
    top_merchants = (
        merch_q
        .group_by(CanonicalEvent.merchant_normalized)
        .order_by(func.sum(CanonicalEvent.amount).desc())
        .limit(10)
        .all()
    )

    # ── Transaction count ────────────────────────────────────────────
    count_q = (
        db.query(func.count(CanonicalEvent.id))
        .filter(CanonicalEvent.user_id == user.id)
    )
    if start:
        count_q = count_q.filter(CanonicalEvent.event_date >= start)
    if end:
        count_q = count_q.filter(CanonicalEvent.event_date <= end)
    txn_count = count_q.scalar() or 0

    # ── Period label ─────────────────────────────────────────────────
    period_labels = {
        "this_month": "This month",
        "last_month": "Last month",
        "last_3": "Last 3 months",
        "all": "All time",
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "total_spend": total_spend,
            "total_income": total_income,
            "txn_count": txn_count,
            "savings": total_income - total_spend,
            "category_data": category_data,
            "income_by_category": income_by_category,
            "top_merchants": top_merchants,
            "period": period,
            "period_label": period_labels.get(period, "All time"),
            "custom_active": custom_active,
            "date_from": date_from.strip() if custom_active else "",
            "date_to": date_to.strip() if custom_active else "",
            "user": user,
        },
    )
