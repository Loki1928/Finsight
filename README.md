# Finsight — Personal Financial Intelligence Platform

> Reconciles transactions across bank statements, wallets, and credit cards into a single authoritative ledger.

**Live demo:** [finsight.onrender.com](https://finsight.onrender.com) *(invite-only, currently in private testing)*


---

## What it does

- **Parses** HDFC bank PDFs (password-protected or plain) and Paytm Excel exports into a structured transaction layer
- **Reconciles** cross-source duplicates (the same UPI payment appearing in both a bank statement and a wallet export) into one canonical event using a 3-level matching engine
- **Tracks** spending by category, top merchants, and account balances — with credit card outstanding handled correctly (bill payments are never double-counted as expenses)

---

## Architecture
