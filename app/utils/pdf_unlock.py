"""Helpers for opening password-protected PDFs."""
from pathlib import Path
import pikepdf


class PDFPasswordRequired(Exception):
    """Raised when a PDF is encrypted and no password was supplied."""


class PDFWrongPassword(Exception):
    """Raised when the supplied password did not unlock the PDF."""


def unlock_pdf(input_path: Path, password: str | None) -> Path:
    """Return a path to a usable (unlocked) PDF.

    If the file is not encrypted, returns the original path.
    If encrypted and password works, writes an unlocked copy and returns its path.
    """
    try:
        with pikepdf.open(input_path):
            return input_path
    except pikepdf.PasswordError:
        if not password:
            raise PDFPasswordRequired()
        try:
            pdf = pikepdf.open(input_path, password=password)
        except pikepdf.PasswordError:
            raise PDFWrongPassword()
        out_path = input_path.with_suffix(".unlocked.pdf")
        pdf.save(out_path)
        pdf.close()
        return out_path
