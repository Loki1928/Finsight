from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db          # adjust import to your actual paths
from app.auth import current_user        # the same helper your other routes use
from app.models.models import Feedback
from app.templates import templates       # however you reference your Jinja templates

router = APIRouter()


@router.get("/feedback")
def feedback_form(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        "feedback.html",
        {"request": request, "user": user, "submitted": False},
    )


@router.post("/feedback")
def submit_feedback(
    request: Request,
    message: str = Form(...),
    page: str = Form(None),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=302)

    fb = Feedback(user_id=user.id, message=message.strip(), page=page)
    db.add(fb)
    db.commit()

    return templates.TemplateResponse(
        "feedback.html",
        {"request": request, "user": user, "submitted": True},
    )