"""Debug endpoints — used during parser development to inspect uploaded PDFs.

Lists uploaded files and dumps the raw table structure pdfplumber extracts
from each page. Not exposed in normal UI. Remove or guard before deploying.
"""
import json
from pathlib import Path
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import pdfplumber
from app.db.session import get_db, DATA_DIR
from app.models.models import Upload
from app.utils.pdf_unlock import unlock_pdf, PDFPasswordRequired, PDFWrongPassword

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

UPLOAD_DIR = DATA_DIR / "uploads"


@router.get("/debug/uploads", response_class=HTMLResponse)
def list_uploads(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Upload).order_by(Upload.uploaded_at.desc()).all()
    return templates.TemplateResponse(
        "debug_uploads.html",
        {"request": request, "rows": rows},
    )


@router.get("/debug/uploads/{upload_id}/dump", response_class=PlainTextResponse)
def dump_upload(upload_id: int, password: str | None = None, db: Session = Depends(get_db)):
    """Dump the raw structure of an uploaded PDF.

    Shows: page count, sample text from the first 2 pages, and every table
    pdfplumber finds on every page (truncated for readability).

    Query param `password` is required if the original PDF was encrypted.
    """
    upload = db.get(Upload, upload_id)
    if not upload:
        raise HTTPException(404, "upload not found")

    # Find the saved file by hash prefix
    matches = list(UPLOAD_DIR.glob(f"{upload.file_hash[:12]}_*"))
    if not matches:
        raise HTTPException(500, f"file for upload {upload_id} not found on disk")

    pdf_path = matches[0]

    try:
        unlocked = unlock_pdf(pdf_path, password)
    except PDFPasswordRequired:
        return PlainTextResponse(
            "PDF is password-protected. Append ?password=YOUR_PASSWORD to the URL.",
            status_code=422,
        )
    except PDFWrongPassword:
        return PlainTextResponse("Wrong password.", status_code=422)

    lines: list[str] = []
    lines.append(f"=== UPLOAD #{upload.id} : {upload.filename} ===")
    lines.append(f"file_hash    : {upload.file_hash}")
    lines.append(f"source_type  : {upload.source_type}")
    lines.append(f"uploaded_at  : {upload.uploaded_at}")
    lines.append("")

    with pdfplumber.open(unlocked) as pdf:
        lines.append(f"page_count   : {len(pdf.pages)}")
        lines.append("")

        # First-page text (truncated)
        first_text = pdf.pages[0].extract_text() or ""
        lines.append("--- FIRST PAGE TEXT (first 1500 chars) ---")
        lines.append(first_text[:1500])
        lines.append("")

        # Tables on every page
        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            lines.append(f"--- PAGE {page_idx + 1} : {len(tables)} table(s) ---")
            for t_idx, table in enumerate(tables):
                lines.append(f"  table {t_idx}: {len(table)} rows x "
                             f"{len(table[0]) if table else 0} cols")
                # Show header row and first 3 data rows
                for r_idx, row in enumerate(table[:4]):
                    truncated = [
                        (cell[:60] + "...") if cell and len(cell) > 60 else cell
                        for cell in row
                    ]
                    lines.append(f"    row {r_idx}: {truncated}")
                if len(table) > 4:
                    lines.append(f"    ... ({len(table) - 4} more rows)")
            lines.append("")

    return PlainTextResponse("\n".join(lines))
