"""Upload endpoint: receives a PDF + optional password, parses, materializes."""
import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Request, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db, DATA_DIR
from app.models.models import Upload, RawTransaction, User
from app.auth.dependencies import require_user
from app.parsers.hdfc_pdf import HDFCBankPDFAdapter
from app.utils.pdf_unlock import PDFPasswordRequired, PDFWrongPassword
from app.db.bootstrap import get_default_account_id
from app.canonical.simple_pass import materialize_canonical

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _serialize_raw_row(raw: dict) -> str:
    """Convert datetime/date objects to ISO strings for JSON storage."""
    out = {}
    for k, v in raw.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return json.dumps(out)


@router.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse("upload.html", {"request": request, "message": None, "user": user})


@router.post("/upload", response_class=HTMLResponse)
async def upload_submit(
    request: Request,
    file: UploadFile = File(...),
    password: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()

    existing = db.query(Upload).filter(Upload.file_hash == file_hash).first()
    if existing:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "message": f"This file was already uploaded (upload #{existing.id})."},
        )

    save_path = UPLOAD_DIR / f"{file_hash[:12]}_{file.filename}"
    save_path.write_bytes(contents)

    account_id = get_default_account_id()
    adapter = HDFCBankPDFAdapter()
    try:
        result = adapter.parse(save_path, password=password)
    except PDFPasswordRequired:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "message": "This PDF is password-protected. Enter the password and re-upload."},
            status_code=422,
        )
    except PDFWrongPassword:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "message": "Wrong password. Try again."},
            status_code=422,
        )

    upload = Upload(
        filename=file.filename,
        file_hash=file_hash,
        source_type="hdfc_pdf",
        account_id=account_id,
        rows_parsed=len(result.transactions),
        rows_skipped=result.rows_skipped,
        parser_version=adapter.parser_version,
        status="success" if not result.warnings else "partial",
        error_log="\n".join(result.warnings) if result.warnings else None,
        user_id=user.id,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    # Persist raw transactions
    for t in result.transactions:
        rt = RawTransaction(
            upload_id=upload.id,
            account_id=account_id,
            source_type="hdfc_pdf",
            txn_date=t.txn_date,
            value_date=t.value_date,
            txn_time=t.txn_time,
            description=t.description,
            amount=t.amount,
            direction=t.direction,
            balance_after=t.balance_after,
            reference_id=t.reference_id,
            upi_id=t.upi_id,
            raw_row_json=_serialize_raw_row(t.raw_row),
            user_id=user.id,
        )
        db.add(rt)
    db.commit()

    # Materialize canonical events (1:1 for V1)
    canonical_count = materialize_canonical(db, upload.id)

    warning_summary = ""
    if result.warnings:
        warning_summary = " Warnings: " + "; ".join(result.warnings[:3])

    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "message": (
                f"Upload #{upload.id} accepted. "
                f"Parsed {upload.rows_parsed} transactions, "
                f"materialized {canonical_count} canonical events.{warning_summary}"
            ),
        },
    )
