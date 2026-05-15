"""Transactions list view."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import CanonicalEvent

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/transactions", response_class=HTMLResponse)
def transactions(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(CanonicalEvent)
        .order_by(CanonicalEvent.event_date.desc())
        .limit(200)
        .all()
    )
    return templates.TemplateResponse(
        "transactions.html",
        {"request": request, "rows": rows},
    )
