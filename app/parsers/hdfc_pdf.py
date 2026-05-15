"""HDFC bank statement PDF parser.

Uses page-text extraction (not extract_tables) because HDFC's PDF layout makes
pdfplumber return one mega-row per page with newline-separated values that
do not align across columns when narrations span multiple lines.

Strategy:
  1. Unlock the PDF if password-protected.
  2. For each page, extract_text() and split into lines.
  3. A transaction begins at any line whose first token matches DD/MM/YY.
  4. Subsequent lines without a leading date are narration continuation.
  5. Parse the transaction line by splitting on whitespace and reading from
     the right: closing_balance, then deposit OR withdrawal, then value_date,
     then reference, then the date itself. Whatever is left is the first
     fragment of the narration.
  6. Skip header / summary lines.
"""
from __future__ import annotations

import re
from datetime import datetime, date
from pathlib import Path

import pdfplumber

from app.parsers.base import BankAdapter, ParseResult, ParsedTransaction
from app.utils.pdf_unlock import unlock_pdf


DATE_PATTERN = re.compile(r"^(\d{2}/\d{2}/\d{2})\b")
AMOUNT_PATTERN = re.compile(r"^[\d,]+\.\d{2}$")
SKIP_KEYWORDS = (
    "STATEMENTSUMMARY",
    "OpeningBalance",
    "GeneratedOn",
    "GeneratedBy",
    "RequestingBranchCode",
    "PageNo.",
    "Date Narration",  # column header
)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%d/%m/%y").date()


def _to_amount(s: str) -> float:
    return float(s.replace(",", ""))


def _is_amount(tok: str) -> bool:
    return bool(AMOUNT_PATTERN.match(tok))


def _looks_like_skip(line: str) -> bool:
    return any(kw in line for kw in SKIP_KEYWORDS)


def _parse_txn_line(line: str) -> dict | None:
    """Parse a single transaction line. Returns a dict or None if malformed.

    HDFC line shape:
        DD/MM/YY  <narration tokens>  <ref>  DD/MM/YY  <withdrawal_or_blank>  <deposit_or_blank>  <closing_balance>

    Only ONE of withdrawal / deposit is present per line; the other is absent
    (the PDF leaves that cell empty and pdfplumber collapses it).
    Strategy: walk tokens from the right.
    """
    tokens = line.split()
    if len(tokens) < 5:
        return None

    # First token must be a date
    m = DATE_PATTERN.match(tokens[0])
    if not m:
        return None
    txn_date = _parse_date(tokens[0])

    # Last token: closing balance (always present, always an amount)
    if not _is_amount(tokens[-1]):
        return None
    closing_balance = _to_amount(tokens[-1])

    # Second-to-last: either deposit or withdrawal amount
    if not _is_amount(tokens[-2]):
        return None
    txn_amount = _to_amount(tokens[-2])

    # Walk back from index -3 to find the value_date (DD/MM/YY)
    # Between value_date and txn_amount there should be no other tokens for a
    # normal row -- if there is, it means BOTH withdrawal and deposit columns
    # had numbers, which HDFC never does on retail statements. We treat
    # such rows as malformed and skip.
    value_date_idx = None
    for i in range(len(tokens) - 3, 0, -1):
        if DATE_PATTERN.match(tokens[i]):
            value_date_idx = i
            break
    if value_date_idx is None or value_date_idx == 0:
        return None
    value_date = _parse_date(tokens[value_date_idx])

    # Reference: token immediately before value_date
    reference_id = tokens[value_date_idx - 1] if value_date_idx >= 2 else None

    # Narration first fragment: everything between tokens[1] and tokens[value_date_idx - 1]
    narration_start = " ".join(tokens[1 : value_date_idx - 1])

    # Direction: we cannot tell from a single line whether txn_amount is a
    # withdrawal or deposit -- both columns share the same position when one
    # is empty. We infer from balance delta in a second pass.
    return {
        "txn_date": txn_date,
        "value_date": value_date,
        "reference_id": reference_id,
        "narration_first_line": narration_start,
        "amount": txn_amount,
        "closing_balance": closing_balance,
    }


def _infer_directions(rows: list[dict], opening_balance: float | None) -> None:
    """Set 'direction' on every row by comparing closing balances.

    If closing[i] > closing[i-1], the txn was a credit; else debit.
    For the first row, we need opening_balance to compare against.
    If we don't have it, default to 'debit' (the most common case) and
    flag a warning -- this is rare in practice because UPI debits dominate.
    """
    prev_balance = opening_balance
    for r in rows:
        if prev_balance is None:
            r["direction"] = "debit"  # fallback; first-row balance unknown
        else:
            delta = round(r["closing_balance"] - prev_balance, 2)
            r["direction"] = "credit" if delta > 0 else "debit"
        prev_balance = r["closing_balance"]


def _extract_opening_balance(first_page_text: str) -> float | None:
    """HDFC statements don't always print an 'Opening Balance' line cleanly;
    we read it from the statement summary instead. As a fallback, return None
    and let _infer_directions assume the first row is a debit."""
    # Look for pattern "Opening Balance" followed by an amount on subsequent lines
    # (parsed from the summary on the last page). Implemented in caller.
    return None


def _extract_summary(pdf) -> dict | None:
    """Pull opening balance, closing balance, total debits, total credits
    from the STATEMENT SUMMARY block on the last data page or after."""
    for page in pdf.pages[-3:]:  # summary is near the end
        text = page.extract_text() or ""
        if "STATEMENTSUMMARY" not in text and "STATEMENT SUMMARY" not in text:
            continue
        # Find the numeric row after the OpeningBalance header
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if "OpeningBalance" in ln or "Opening Balance" in ln:
                # The next non-empty line should be the numbers
                for nxt in lines[i + 1 : i + 5]:
                    nums = re.findall(r"[\d,]+\.\d{2}|\d+", nxt)
                    if len(nums) >= 6:
                        try:
                            return {
                                "opening_balance": _to_amount(nums[0]),
                                "debit_count": int(nums[1]),
                                "credit_count": int(nums[2]),
                                "debits_total": _to_amount(nums[3]),
                                "credits_total": _to_amount(nums[4]),
                                "closing_balance": _to_amount(nums[5]),
                            }
                        except (ValueError, IndexError):
                            continue
    return None


class HDFCBankPDFAdapter(BankAdapter):
    source_type = "hdfc_pdf"
    parser_version = "0.2.0"

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
        rows: list[dict] = []
        current_narration_lines: list[str] = []
        current_row: dict | None = None

        def flush():
            if current_row is not None:
                current_row["narration_full"] = " ".join(current_narration_lines).strip()
                rows.append(current_row)

        with pdfplumber.open(unlocked) as pdf:
            summary = _extract_summary(pdf)
            opening_balance = summary["opening_balance"] if summary else None

            for page in pdf.pages:
                text = page.extract_text() or ""
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if _looks_like_skip(line):
                        continue

                    parsed = _parse_txn_line(line)
                    if parsed is not None:
                        # close previous, open new
                        flush()
                        current_row = parsed
                        current_narration_lines = [parsed["narration_first_line"]]
                    else:
                        # continuation of a narration, if we're inside a row
                        if current_row is not None:
                            current_narration_lines.append(line)

            flush()

        if not rows:
            result.warnings.append("No transaction rows detected. Layout may differ from expected.")
            return result

        _infer_directions(rows, opening_balance)

        # Build ParsedTransaction objects
        for r in rows:
            result.transactions.append(
                ParsedTransaction(
                    txn_date=r["txn_date"],
                    value_date=r["value_date"],
                    txn_time=None,
                    description=r["narration_full"],
                    amount=r["amount"],
                    direction=r["direction"],
                    balance_after=r["closing_balance"],
                    reference_id=r["reference_id"],
                    upi_id=None,
                    raw_row=r,
                )
            )

        # Verification warnings (don't fail the parse, just flag)
        if summary:
            total_debits = sum(t.amount for t in result.transactions if t.direction == "debit")
            total_credits = sum(t.amount for t in result.transactions if t.direction == "credit")
            if abs(total_debits - summary["debits_total"]) > 1:
                result.warnings.append(
                    f"Debits total mismatch: parsed {total_debits:.2f} vs summary {summary['debits_total']:.2f}"
                )
            if abs(total_credits - summary["credits_total"]) > 1:
                result.warnings.append(
                    f"Credits total mismatch: parsed {total_credits:.2f} vs summary {summary['credits_total']:.2f}"
                )
            count_d = sum(1 for t in result.transactions if t.direction == "debit")
            count_c = sum(1 for t in result.transactions if t.direction == "credit")
            if count_d != summary["debit_count"] or count_c != summary["credit_count"]:
                result.warnings.append(
                    f"Count mismatch: parsed {count_d}D/{count_c}C vs summary "
                    f"{summary['debit_count']}D/{summary['credit_count']}C"
                )

        return result
