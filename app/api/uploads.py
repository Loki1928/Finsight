"""Upload endpoint: receives a PDF + optional password, stores audit row."""
import hashlib
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db.session import get_db, DATA_DIR
from app.models.models import Upload
from app.parsers.hdfc_pdf import HDFCBankPDFAdapter
from app.utils.pdf_unlock import PDFPasswordRequired, PDFWrongPassword

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request, "message": None})


@router.post("/upload", response_class=HTMLResponse)
async def upload_submit(
    request: Request,
    file: UploadFile = File(...),
    password: str | None = Form(None),
    db: Session = Depends(get_db),
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
        rows_parsed=len(result.transactions),
        rows_skipped=result.rows_skipped,
        parser_version=adapter.parser_version,
        status="success" if not result.warnings else "partial",
        error_log="\n".join(result.warnings) if result.warnings else None,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "message": (
                f"Upload #{upload.id} accepted. "
                f"Parsed {upload.rows_parsed} rows. "
                f"Note: real parsing logic is added in Step 6."
            ),
        },
    )
