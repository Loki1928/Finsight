"""Transactions list + manual-add / edit / delete / recategorize / notes."""
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
    "Entertainment", "Travel", "Bill Payment", "Transfer",
    "P2P Transfer", "Income", "Investments", "Loans/EMI",
    "Bank Charges", "Utilities", "Rent", "Medical", "Education",
    "Subscriptions", "Insurance", "Government", "Owner's Drawing", "Other",
]
_CATEGORY_LOOKUP = {s.lower(): s for s in CATEGORY_SUGGESTIONS}


def _norm_cat(raw: str) -> str:
    c = raw.strip()
    return _CATEGORY_LOOKUP.get(c.lower(), c.title()) if c else ""


def _get_editable(db, event_id, user_id):
    e = db.query(CanonicalEvent).filter(
        CanonicalEvent.id == event_id, CanonicalEvent.user_id == user_id
    ).first()
    if not e:
        raise HTTPException(404, "Transaction not found")
    if not e.is_user_edited:
        raise HTTPException(403, "Parsed transactions cannot be fully edited.")
    return e


def _get_any(db, event_id, user_id):
    e = db.query(CanonicalEvent).filter(
        CanonicalEvent.id == event_id, CanonicalEvent.user_id == user_id
    ).first()
    if not e:
        raise HTTPException(404, "Transaction not found")
    return e


@router.get("/transactions", response_class=HTMLResponse)
def transactions(
    request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_user),
    q: str = Query(""), category: str = Query(""),
    direction: str = Query(""), date_from: str = Query(""), date_to: str = Query(""),
):
    qry = db.query(CanonicalEvent).filter(CanonicalEvent.user_id == user.id)
    if q.strip():
        s = f"%{q.strip()}%"
        qry = qry.filter(
            CanonicalEvent.merchant_normalized.ilike(s)
            | CanonicalEvent.merchant_raw.ilike(s)
            | CanonicalEvent.notes.ilike(s)
            | CanonicalEvent.generated_description.ilike(s)
        )
    if category.strip():
        if category.strip().lower() == "uncategorized":
            qry = qry.filter(
                (CanonicalEvent.category.is_(None))
                | (CanonicalEvent.category == "")
                | (CanonicalEvent.category == "Uncategorized")
            )
        else:
            qry = qry.filter(CanonicalEvent.category == category.strip())
    if direction in ("debit", "credit"):
        qry = qry.filter(CanonicalEvent.direction == direction)
    if date_from.strip():
        try:
            qry = qry.filter(CanonicalEvent.event_date >= date.fromisoformat(date_from.strip()))
        except ValueError:
            pass
    if date_to.strip():
        try:
            qry = qry.filter(CanonicalEvent.event_date <= date.fromisoformat(date_to.strip()))
        except ValueError:
            pass

    rows = qry.order_by(CanonicalEvent.event_date.desc(), CanonicalEvent.id.desc()).all()
    debits = [r for r in rows if r.direction == "debit"]
    credits = [r for r in rows if r.direction == "credit"]

    latest_upload = (
        db.query(Upload).filter(Upload.user_id == user.id)
        .order_by(Upload.uploaded_at.desc()).first()
    )
    cat_rows = (
        db.query(CanonicalEvent.category)
        .filter(CanonicalEvent.user_id == user.id)
        .filter(CanonicalEvent.category.isnot(None))
        .filter(CanonicalEvent.category != "")
        .filter(CanonicalEvent.category != "Uncategorized")
        .distinct().order_by(CanonicalEvent.category).all()
    )
    category_list = sorted(set(c[0] for c in cat_rows if c[0]))

    summary = {
        "total_count": len(rows),
        "debit_count": len(debits),
        "credit_count": len(credits),
        "debits_total": sum(r.amount for r in debits),
        "credits_total": sum(r.amount for r in credits),
        "net": sum(r.amount for r in credits) - sum(r.amount for r in debits),
        "manual_count": sum(1 for r in rows if r.is_user_edited),
        "upload_status": latest_upload.status if latest_upload else None,
        "upload_warnings": latest_upload.error_log if latest_upload else None,
        "filename": latest_upload.filename if latest_upload else None,
    }
    filters = {
        "q": q.strip(), "category": category.strip(),
        "direction": direction, "date_from": date_from.strip(), "date_to": date_to.strip(),
    }
    return templates.TemplateResponse("transactions.html", {
        "request": request, "rows": rows, "summary": summary,
        "filters": filters, "category_list": category_list,
        "category_suggestions": CATEGORY_SUGGESTIONS,
    })


@router.post("/transactions/{event_id}/recategorize")
def recategorize(event_id: int, category: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_user)):
    e = _get_any(db, event_id, user.id)
    nc = _norm_cat(category)
    if nc:
        e.category = nc
        e.is_user_edited = 1  # protect from re-apply-all
    else:
        categorize_event(e, db)
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


@router.post("/transactions/{event_id}/notes")
def save_notes(event_id: int, notes: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_user)):
    e = _get_any(db, event_id, user.id)
    e.notes = notes.strip() or None
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


@router.get("/transactions/add", response_class=HTMLResponse)
def add_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    accounts = db.query(Account).filter(Account.is_active == 1).order_by(Account.id).all()
    return templates.TemplateResponse("transactions_add.html", {
        "request": request, "accounts": accounts, "today": date.today().isoformat(),
    })


@router.post("/transactions/add")
def add_submit(
    event_date: str = Form(...), amount: float = Form(..., gt=0),
    direction: str = Form(...), account_id: int = Form(...),
    merchant: str = Form(""), category: str = Form(""), notes: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    if direction not in ("debit", "credit"):
        return RedirectResponse(url="/transactions/add", status_code=303)
    try:
        parsed_date = date.fromisoformat(event_date)
    except ValueError:
        return RedirectResponse(url="/transactions/add", status_code=303)
    e = CanonicalEvent(
        event_date=parsed_date, amount=amount, direction=direction,
        primary_account_id=account_id, merchant_raw=merchant.strip() or None,
        notes=notes.strip() or None, is_user_edited=1, confidence_score=1.0, user_id=user.id,
    )
    categorize_event(e, db)
    uc = _norm_cat(category)
    if uc:
        e.category = uc
    db.add(e)
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


@router.get("/transactions/{event_id}/edit", response_class=HTMLResponse)
def edit_form(event_id: int, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_user)):
    e = _get_editable(db, event_id, user.id)
    accounts = db.query(Account).filter(Account.is_active == 1).order_by(Account.id).all()
    return templates.TemplateResponse("transactions_edit.html", {
        "request": request, "event": e, "accounts": accounts,
    })


@router.post("/transactions/{event_id}/edit")
def edit_submit(
    event_id: int, event_date: str = Form(...), amount: float = Form(..., gt=0),
    direction: str = Form(...), account_id: int = Form(...),
    merchant: str = Form(""), category: str = Form(""), notes: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    e = _get_editable(db, event_id, user.id)
    if direction not in ("debit", "credit"):
        return RedirectResponse(url=f"/transactions/{event_id}/edit", status_code=303)
    try:
        parsed_date = date.fromisoformat(event_date)
    except ValueError:
        return RedirectResponse(url=f"/transactions/{event_id}/edit", status_code=303)
    e.event_date = parsed_date
    e.amount = amount
    e.direction = direction
    e.primary_account_id = account_id
    e.merchant_raw = merchant.strip() or None
    e.notes = notes.strip() or None
    categorize_event(e, db)
    uc = _norm_cat(category)
    if uc:
        e.category = uc
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


@router.post("/transactions/{event_id}/delete")
def delete(event_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    e = _get_editable(db, event_id, user.id)
    db.delete(e)
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)
