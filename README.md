# Finsight — Personal Financial Intelligence Platform

> Reconciles transactions across bank statements, wallets, and credit cards into a single authoritative ledger.

**Live demo:** [finsight-al2x.onrender.com](https://finsight-al2x.onrender.com) *(invite-only, currently in private testing)*


---

## What it does

- **Parses** HDFC bank PDFs (password-protected or plain) and Paytm Excel exports into a structured transaction layer
- **Reconciles** cross-source duplicates (the same UPI payment appearing in both a bank statement and a wallet export) into one canonical event using a 3-level matching engine
- **Tracks** spending by category, top merchants, and account balances — with credit card outstanding handled correctly (bill payments are never double-counted as expenses)

---

## Architecture

User uploads PDF/Excel
│
▼
Raw transaction layer  (immutable; one row per source row)
│
▼
Reconciliation engine  (Level 1: exact ID → Level 2: narration route → Level 3: contextual score)
│
▼
Canonical events layer  (deduplicated, authoritative; all analytics read from here)
│
▼
Dashboard / Analytics

---

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python 3.11) |
| Frontend | Jinja2 templates + Tailwind CSS |
| Database | Neon Postgres (Postgres 18, AWS ap-southeast-1) |
| Auth | Google OAuth 2.0 (invite-only allowlist) |
| Hosting | Render (Docker) |
| PDF parsing | pdfplumber + pikepdf (password-protected PDFs) |
| Reconciliation | rapidfuzz (fuzzy merchant matching) |

---

## Status

Private beta — invite-only testing with a small group. Not open for public signups yet.

**V1 complete:** HDFC parser · Paytm parser · 3-level reconciliation · Dashboard · Credit card intelligence · User auth + delete-account (DPDP erasure right)

**V2 planned:** AI copilot · Goal tracker · Manual investments / net worth · Recurring detection · Budget engine · Additional bank parsers

---

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — source-available for noncommercial use. Copyright 2026 Lokendra Sharma.
