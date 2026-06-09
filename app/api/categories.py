"""Category management: view all, rename, re-run auto-categorization.

Session 19 addition. Gives testers a single place to see and fix categories.
"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import CanonicalEvent, User
from app.auth.dependencies import require_user
from app.canonical.categorize import categorize_event

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/categories", response_class=HTMLResponse)
def categories_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Show all categories with transaction counts and totals."""
    rows = (
        db.query(
            CanonicalEvent.category,
            func.count(CanonicalEvent.id).label("count"),
            func.sum(CanonicalEvent.amount).label("total"),
        )
        .filter(CanonicalEvent.user_id == user.id)
        .group_by(CanonicalEvent.category)
        .order_by(func.count(CanonicalEvent.id).desc())
        .all()
    )

    categories = []
    for row in rows:
        categories.append({
            "name": row.category or "Uncategorized",
            "is_uncategorized": (row.category is None or row.category == "" or row.category == "Uncategorized"),
            "count": row.count,
            "total": row.total or 0,
        })

    total_txns = sum(c["count"] for c in categories)
    uncategorized_count = sum(c["count"] for c in categories if c["is_uncategorized"])

    return templates.TemplateResponse(
        "categories.html",
        {
            "request": request,
            "categories": categories,
            "total_txns": total_txns,
            "uncategorized_count": uncategorized_count,
        },
    )


@router.post("/categories/rename")
def categories_rename(
    old_name: str = Form(...),
    new_name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Rename all transactions from one category to another."""
    new_clean = new_name.strip()
    if not new_clean:
        return RedirectResponse(url="/categories", status_code=303)

    # Handle "Uncategorized" as None in DB
    if old_name.strip() == "Uncategorized":
        db.query(CanonicalEvent).filter(
            CanonicalEvent.user_id == user.id,
            (CanonicalEvent.category.is_(None))
            | (CanonicalEvent.category == "")
            | (CanonicalEvent.category == "Uncategorized"),
        ).update({"category": new_clean}, synchronize_session="fetch")
    else:
        db.query(CanonicalEvent).filter(
            CanonicalEvent.user_id == user.id,
            CanonicalEvent.category == old_name.strip(),
        ).update({"category": new_clean}, synchronize_session="fetch")

    db.commit()
    return RedirectResponse(url="/categories", status_code=303)


@router.post("/categories/recategorize-all")
def recategorize_all(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Re-run auto-categorization on ALL transactions for this user.
    Uses the latest merchant_normalizer patterns. Only changes category
    and merchant_normalized — does not touch amounts, dates, or other fields.
    Skips transactions where category was manually set by the user (is_user_edited=1
    AND category is not null/empty)."""
    events = (
        db.query(CanonicalEvent)
        .filter(CanonicalEvent.user_id == user.id)
        .all()
    )

    updated = 0
    for event in events:
        old_category = event.category
        categorize_event(event)
        if event.category != old_category:
            updated += 1

    db.commit()
    return RedirectResponse(url="/categories", status_code=303)
