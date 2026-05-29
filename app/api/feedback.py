from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import Feedback, User
from app.auth.dependencies import require_user

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/feedback", response_class=HTMLResponse)
def feedback_form(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        "feedback.html",
        {"request": request, "user": user, "submitted": False},
    )


@router.post("/feedback", response_class=HTMLResponse)
def submit_feedback(
    request: Request,
    message: str = Form(...),
    page: str = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    fb = Feedback(user_id=user.id, message=message.strip(), page=page)
    db.add(fb)
    db.commit()
    return templates.TemplateResponse(
        "feedback.html",
        {"request": request, "user": user, "submitted": True},
    )