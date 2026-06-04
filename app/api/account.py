# app/api/account.py
import os
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from app.auth.dependencies import require_user
from app.db.session import get_db
from app.models.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse("privacy.html", {"request": request, "user": user})


@router.get("/account", response_class=HTMLResponse)
def account(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(
        "account.html", {"request": request, "user": user, "error": None}
    )


@router.post("/account/delete")
def account_delete(
    request: Request,
    confirm_text: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if confirm_text.strip() != "DELETE":
        return templates.TemplateResponse(
            "account.html",
            {"request": request, "user": user,
             "error": "Please type DELETE exactly to confirm."},
            status_code=400,
        )

    uid = user.id

    # Collect any explicit file paths to remove AFTER the DB delete succeeds.
    file_paths = []
    upload_rows = db.execute(
        text("SELECT * FROM uploads WHERE user_id = :uid"), {"uid": uid}
    ).mappings().all()
    data_dir = os.environ.get("DATA_DIR", "data")
    for row in upload_rows:
        for key in ("file_path", "path", "filepath", "stored_path"):
            val = row.get(key)
            if val:
                file_paths.append(str(val))

  # reconciliation_queue (if it exists) references raw_transactions — clear it first.
    # Use the dialect-agnostic inspector instead of sqlite_master (Postgres has no sqlite_master).
    has_queue = inspect(db.get_bind()).has_table("reconciliation_queue")
    if has_queue:
        db.execute(text("""
            DELETE FROM reconciliation_queue
            WHERE raw_a_id IN (SELECT id FROM raw_transactions WHERE user_id = :uid)
               OR raw_b_id IN (SELECT id FROM raw_transactions WHERE user_id = :uid)
        """), {"uid": uid})

    # Children before parents: raw_transactions references canonical_events + uploads,
    # so it MUST be deleted before them.
    for table in ("raw_transactions", "canonical_events", "uploads", "feedback"):
        db.execute(text(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": uid})
    db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    db.commit()

    # DB delete committed — now best-effort removal of any files on disk.
    for p in file_paths:
        for candidate in (p, os.path.join(data_dir, p)):
            if os.path.isfile(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

  