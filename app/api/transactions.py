"""Transactions list view + manual-add / edit / delete / recategorize handlers.

Session 19 changes:
  - Fixed security bug: edit POST handler now requires user auth + passes user_id
  - Added /transactions/{id}/recategorize — works on ALL transactions (parsed + manual)
  - Added search/filter support: q, category, direction, date_from, date_to query params
  - Sort order changed to newest-first (was oldest-first)
  - Added category_list and category_suggestions to template context
"""
from datetime import date
from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import CanonicalEvent, Upload, Account, User
from app.auth.dependencies import require_user
from app.canonical.categorize import categorize_event

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

CATEGORY_SUGGESTIONS = [
    "Cash Spend", "Food", "Fuel", "Groceries", "Shopping",
    "Entertainment", "Travel", "Bill Payment", "Bill Payment (CRED)",
    "Transfer", "P2P Transfer", "Income", "Investments", "Loans/EMI",
    "Bank Charges", "Utilities", "Rent", "Medical", "Education",
    "Subscriptions", "Other",
]
_CATEGORY_LOOKUP = {s.lower(): s for s in CATEGORY_SUGGESTIONS}


def _normalize_user_category(raw: str) -> str:
    cleaned = raw.strip()
    if not cleaned:
        return ""
    return _CATEGORY_LOOKUP.get(cleaned.lower(), cleaned.title())


def _get_user_editable_event(db: Session, event_id: int, user_id: int) -> CanonicalEvent:
    event = db.query(CanonicalEvent).filter(
        CanonicalEvent.id == event_id,
        CanonicalEvent.user_id == user_id,
    ).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if not event.is_user_edited:
        raise HTTPException(
            status_code=403,
            detail="This transaction came from a parsed statement and cannot be edited here.",
        )
    return event


# ── Transaction list with search + filters ───────────────────────────

@router.get("/transactions", response_class=HTMLResponse)
def transactions(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    q: str = Query("", description="Search merchant/description"),
    category: str = Query("", description="Filter by category"),
    direction: str = Query("", description="Filter debit/credit"),
    date_from: str = Query("", description="Start date YYYY-MM-DD"),
    date_to: str = Query("", description="End date YYYY-MM-DD"),
):
    query = db.query(CanonicalEvent).filter(CanonicalEvent.user_id == user.id)

    # Text search
    if q.strip():
        search = f"%{q.strip()}%"
        query = query.filter(
            (CanonicalEvent.merchant_normalized.ilike(search))
            | (CanonicalEvent.merchant_raw.ilike(search))
            | (CanonicalEvent.notes.ilike(search))
        )

    # Category filter
    if category.strip():
        if category.strip().lower() == "uncategorized":
            query = query.filter(
                (CanonicalEvent.category.is_(None))
                | (CanonicalEvent.category == "")
                | (CanonicalEvent.category == "Uncategorized")
            )
        else:
            query = query.filter(CanonicalEvent.category == category.strip())

    # Direction filter
    if direction in ("debit", "credit"):
        query = query.filter(CanonicalEvent.direction == direction)

    # Date range
    if date_from.strip():
        try:
            query = query.filter(CanonicalEvent.event_date >= date.fromisoformat(date_from.strip()))
        except ValueError:
            pass
    if date_to.strip():
        try:
            query = query.filter(CanonicalEvent.event_date <= date.fromisoformat(date_to.strip()))
        except ValueError:
            pass

    rows = query.order_by(CanonicalEvent.event_date.desc(), CanonicalEvent.id.desc()).all()

    # Summary stats on filtered results
    total_count = len(rows)
    debits = [r for r in rows if r.direction == "debit"]
    credits = [r for r in rows if r.direction == "credit"]
    debits_total = sum(r.amount for r in debits)
    credits_total = sum(r.amount for r in credits)
    manual_count = sum(1 for r in rows if r.is_user_edited)

    latest_upload = (
        db.query(Upload)
        .filter(Upload.user_id == user.id)
        .order_by(Upload.uploaded_at.desc())
        .first()
    )

    # Distinct categories for filter dropdown
    all_categories = (
        db.query(CanonicalEvent.category)
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.category.isnot(None))
        .filter(CanonicalEvent.category != "")
        .filter(CanonicalEvent.category != "Uncategorized")
        .distinct()
        .order_by(CanonicalEvent.category)
        .all()
    )
    category_list = sorted(set(c[0] for c in all_categories if c[0]))

    summary = {
        "total_count": total_count,
        "debit_count": len(debits),
        "credit_count": len(credits),
        "debits_total": debits_total,
        "credits_total": credits_total,
        "net": credits_total - debits_total,
        "manual_count": manual_count,
        "upload_status": latest_upload.status if latest_upload else None,
        "upload_warnings": latest_upload.error_log if latest_upload else None,
        "filename": latest_upload.filename if latest_upload else None,
    }

    filters = {
        "q": q.strip(),
        "category": category.strip(),
        "direction": direction,
        "date_from": date_from.strip(),
        "date_to": date_to.strip(),
    }

    return templates.TemplateResponse(
        "transactions.html",
        {
            "request": request,
            "rows": rows,
            "summary": summary,
            "filters": filters,
            "category_list": category_list,
            "category_suggestions": CATEGORY_SUGGESTIONS,
        },
    )


# ── Recategorize ANY transaction (parsed or manual) ──────────────────

@router.post("/transactions/{event_id}/recategorize")
def transactions_recategorize(
    event_id: int,
    category: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Change category on any transaction. This is the key tester feature —
    lets users fix auto-categorization on parsed rows without needing full edit."""
    event = db.query(CanonicalEvent).filter(
        CanonicalEvent.id == event_id,
        CanonicalEvent.user_id == user.id,
    ).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    new_category = _normalize_user_category(category)
    if new_category:
        event.category = new_category
    else:
        categorize_event(event)

    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


# ── Manual transaction CRUD ──────────────────────────────────────────

@router.get("/transactions/add", response_class=HTMLResponse)
def transactions_add_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    accounts = (
        db.query(Account)
        .filter(Account.is_active == 1)
        .order_by(Account.id.asc())
        .all()
    )
    return templates.TemplateResponse(
        "transactions_add.html",
        {
            "request": request,
            "accounts": accounts,
            "today": date.today().isoformat(),
        },
    )


@router.post("/transactions/add")
def transactions_add_submit(
    event_date: str = Form(...),
    amount: float = Form(..., gt=0),
    direction: str = Form(...),
    account_id: int = Form(...),
    merchant: str = Form(""),
    category: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if direction not in ("debit", "credit"):
        return RedirectResponse(url="/transactions/add", status_code=303)
    try:
        parsed_date = date.fromisoformat(event_date)
    except ValueError:
        return RedirectResponse(url="/transactions/add", status_code=303)

    event = CanonicalEvent(
        event_date=parsed_date,
        amount=amount,
        direction=direction,
        primary_account_id=account_id,
        merchant_raw=merchant.strip() or None,
        notes=notes.strip() or None,
        is_user_edited=1,
        confidence_score=1.0,
        user_id=user.id,
    )
    categorize_event(event)
    user_category = _normalize_user_category(category)
    if user_category:
        event.category = user_category

    db.add(event)
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


@router.get("/transactions/{event_id}/edit", response_class=HTMLResponse)
def transactions_edit_form(event_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    event = _get_user_editable_event(db, event_id, user.id)
    accounts = (
        db.query(Account)
        .filter(Account.is_active == 1)
        .order_by(Account.id.asc())
        .all()
    )
    return templates.TemplateResponse(
        "transactions_edit.html",
        {"request": request, "event": event, "accounts": accounts},
    )


@router.post("/transactions/{event_id}/edit")
def transactions_edit_submit(
    event_id: int,
    event_date: str = Form(...),
    amount: float = Form(..., gt=0),
    direction: str = Form(...),
    account_id: int = Form(...),
    merchant: str = Form(""),
    category: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),  # FIXED: was missing in original
):
    event = _get_user_editable_event(db, event_id, user.id)  # FIXED: now passes user.id
    if direction not in ("debit", "credit"):
        return RedirectResponse(url=f"/transactions/{event_id}/edit", status_code=303)
    try:
        parsed_date = date.fromisoformat(event_date)
    except ValueError:
        return RedirectResponse(url=f"/transactions/{event_id}/edit", status_code=303)

    event.event_date = parsed_date
    event.amount = amount
    event.direction = direction
    event.primary_account_id = account_id
    event.merchant_raw = merchant.strip() or None
    event.notes = notes.strip() or None

    categorize_event(event)
    user_category = _normalize_user_category(category)
    if user_category:
        event.category = user_category

    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


@router.post("/transactions/{event_id}/delete")
def transactions_delete(event_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    event = _get_user_editable_event(db, event_id, user.id)
    db.delete(event)
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)
