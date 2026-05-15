"""Transactions list view with verification summary."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import CanonicalEvent, Upload

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/transactions", response_class=HTMLResponse)
def transactions(request: Request, db: Session = Depends(get_db)):
    # Chronological order to match PDF reading order
    rows = (
        db.query(CanonicalEvent)
        .order_by(CanonicalEvent.event_date.asc(), CanonicalEvent.id.asc())
        .all()
    )

    # Summary stats
    total_count = len(rows)
    debits = [r for r in rows if r.direction == "debit"]
    credits = [r for r in rows if r.direction == "credit"]
    debit_count = len(debits)
    credit_count = len(credits)
    debits_total = sum(r.amount for r in debits)
    credits_total = sum(r.amount for r in credits)

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
        "upload_status": latest_upload.status if latest_upload else None,
        "upload_warnings": latest_upload.error_log if latest_upload else None,
        "filename": latest_upload.filename if latest_upload else None,
    }

    return templates.TemplateResponse(
        "transactions.html",
        {"request": request, "rows": rows, "summary": summary},
    )
