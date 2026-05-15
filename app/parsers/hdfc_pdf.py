"""HDFC bank statement PDF parser. Stub — real logic fills in at Step 6."""
from pathlib import Path
import pdfplumber
from app.parsers.base import BankAdapter, ParseResult
from app.utils.pdf_unlock import unlock_pdf


class HDFCBankPDFAdapter(BankAdapter):
    source_type = "hdfc_pdf"
    parser_version = "0.1.0-stub"

    def can_handle(self, file_path: Path) -> bool:
        try:
            with pdfplumber.open(file_path) as pdf:
                first = pdf.pages[0].extract_text() or ""
            return "HDFC" in first.upper()
        except Exception:
            return False

    def parse(self, file_path: Path, password: str | None = None) -> ParseResult:
        unlocked = unlock_pdf(file_path, password)
        result = ParseResult()
        with pdfplumber.open(unlocked) as pdf:
            result.warnings.append(
                f"Stub parser: opened PDF with {len(pdf.pages)} pages. "
                "Real extraction logic comes in Step 6."
            )
        return result
