"""Transactions list view + manual-add / edit / delete handlers."""
from datetime import date
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import CanonicalEvent, Upload, Account, User
from app.auth.dependencies import require_user
from app.canonical.categorize import categorize_event

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Built-in category suggestions. Mirrors the <datalist> in transactions_add.html
# and transactions_edit.html. Used to canonicalize user input so 'BILL PAYMENT (CRED)'
# stays 'Bill Payment (CRED)' rather than getting title-cased to 'Bill Payment (Cred)'.
CATEGORY_SUGGESTIONS = [
    "Cash Spend", "Food", "Fuel", "Groceries", "Shopping",
    "Entertainment", "Travel", "Bill Payment (CRED)", "Transfer",
    "P2P Transfer", "Income", "Investments", "Loans/EMI",
    "Bank Charges", "Other",
]
_CATEGORY_LOOKUP = {s.lower(): s for s in CATEGORY_SUGGESTIONS}


def _normalize_user_category(raw: str) -> str:
    """Strip + canonicalize a user-entered category string.

    If the cleaned value matches a known suggestion case-insensitively,
    return its canonical form (so 'CRED' stays as 'CRED', etc.).
    Otherwise title-case it so 'pet supplies' / 'Pet supplies' / ' PET SUPPLIES '
    all collapse to 'Pet Supplies'. Returns '' if blank.
    """
    cleaned = raw.strip()
    if not cleaned:
        return ""
    return _CATEGORY_LOOKUP.get(cleaned.lower(), cleaned.title())


def _get_user_editable_event(db: Session, event_id: int) -> CanonicalEvent:
    """Fetch a canonical event by id, but ONLY if it's user-editable.

    Parsed events (is_user_edited=0) cannot be edited or deleted via this UI —
    that's a separate feature with different rules (would orphan raw_transactions
    rows). The progress file defers parsed-row editing to a later phase.
    """
    event = db.query(CanonicalEvent).filter(CanonicalEvent.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if not event.is_user_edited:
        raise HTTPException(
            status_code=403,
            detail="This transaction came from a parsed statement and cannot be edited here.",
        )
    return event


@router.get("/transactions", response_class=HTMLResponse)
def transactions(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    # Chronological order to match PDF reading order
    rows = (
        db.query(CanonicalEvent)
        .filter(CanonicalEvent.user_id == user.id)
        .order_by(CanonicalEvent.event_date.asc(), CanonicalEvent.id.asc())
        .all()
    )
    # Summary stats
   # Summary stats
    total_count = len(rows)
    debits = [r for r in rows if r.direction == "debit"]
    credits = [r for r in rows if r.direction == "credit"]
    debit_count = len(debits)
    credit_count = len(credits)
    debits_total = sum(r.amount for r in debits)
    credits_total = sum(r.amount for r in credits)
    # Manual-entry count — surfaces how much of the data is user-added vs parsed.
    manual_count = sum(1 for r in rows if r.is_user_edited)
    # Most recent upload — used to show "expected" numbers from the PDF summary,
    # if the parser captured them in error_log warnings (it would only do this on
    # mismatch). When no warnings, we just show "matches".
    latest_upload = (
        db.query(Upload)
        .order_by(Upload.uploaded_at.desc())
        .first()
    )
    summary = {
        "total_count": total_count,
        "debit_count": debit_count,
        "credit_count": credit_count,
        "debits_total": debits_total,
        "credits_total": credits_total,
        "net": credits_total - debits_total,
        "manual_count": manual_count,
        "upload_status": latest_upload.status if latest_upload else None,
        "upload_warnings": latest_upload.error_log if latest_upload else None,
        "filename": latest_upload.filename if latest_upload else None,
    }
    return templates.TemplateResponse(
        "transactions.html",
        {"request": request, "rows": rows, "summary": summary},
    )


@router.get("/transactions/add", response_class=HTMLResponse)
def transactions_add_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Render the manual-entry form."""
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
    """Persist a user-entered transaction as a CanonicalEvent.

    Manual entries have is_user_edited=1, no upload_id, and no linked raw_row.
    The canonical_events schema was designed for this from day one — these
    fields are the seam that lets manual entries coexist with parsed ones.
    """
    if direction not in ("debit", "credit"):
        return RedirectResponse(url="/transactions/add", status_code=303)

    try:
        parsed_date = date.fromisoformat(event_date)
    except ValueError:
        return RedirectResponse(url="/transactions/add", status_code=303)

    merchant_clean = merchant.strip() or None
    notes_clean = notes.strip() or None

    event = CanonicalEvent(
        event_date=parsed_date,
        amount=amount,
        direction=direction,
        primary_account_id=account_id,
        merchant_raw=merchant_clean,
        notes=notes_clean,
        is_user_edited=1,
        confidence_score=1.0,
        user_id=user.id,
    )

    # Always run the categorizer so merchant_normalized is populated regardless
    # of whether the user supplied a category. If they did, we override the
    # category after (but keep the normalized merchant the categorizer derived).
    categorize_event(event)

    user_category = _normalize_user_category(category)
    if user_category:
        event.category = user_category

    db.add(event)
    db.commit()

    return RedirectResponse(url="/transactions", status_code=303)


@router.get("/transactions/{event_id}/edit", response_class=HTMLResponse)
def transactions_edit_form(event_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Render the edit form for a user-entered transaction."""
    event = _get_user_editable_event(db, event_id)
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
):
    """Update a user-entered CanonicalEvent.

    Same input rules as the add handler. If the user clears the category,
    we re-run the categorizer on the new merchant so the field doesn't end
    up stale. is_user_edited stays 1 — once manual, always manual.
    """
    event = _get_user_editable_event(db, event_id)

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

    user_category = _normalize_user_category(category)
    if user_category:
        # User specified a category — honor it, but still refresh merchant_normalized
        # from the (possibly changed) merchant_raw.
        categorize_event(event)
        event.category = user_category
    else:
        # User cleared the category — re-run auto-detect on the new merchant.
        categorize_event(event)

    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


@router.post("/transactions/{event_id}/delete")
def transactions_delete(event_id: int, db: Session = Depends(get_db)):
    """Permanently delete a user-entered CanonicalEvent.

    Parsed events are protected by _get_user_editable_event — attempting to
    delete one returns 403 rather than silently removing parser-sourced data.
    """
    event = _get_user_editable_event(db, event_id)
    db.delete(event)
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)