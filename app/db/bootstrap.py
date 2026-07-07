"""Idempotent bootstrap: ensures default accounts exist on startup.
Runs at app startup. Safe to call repeatedly — checks for existence first.
"""
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.models import Account

DEFAULT_HDFC_ACCOUNT_NAME = "HDFC Savings (default)"
DEFAULT_CASH_ACCOUNT_NAME = "Cash"


def ensure_default_account() -> int:
    """Insert the default HDFC account if it doesn't exist. Returns its id."""
    db: Session = SessionLocal()
    try:
        existing = (
            db.query(Account)
            .filter(Account.name == DEFAULT_HDFC_ACCOUNT_NAME)
            .first()
        )
        if existing:
            return existing.id
        account = Account(
            name=DEFAULT_HDFC_ACCOUNT_NAME,
            type="bank",
            institution="HDFC",
            account_mask=None,
            currency="INR",
            opening_balance=0.0,
            is_active=1,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account.id
    finally:
        db.close()


def ensure_default_cash_account() -> int:
    """Insert the default Cash account if it doesn't exist. Returns its id.

    Cash is a first-class account, same as HDFC. It holds manual-entry
    transactions that have no statement source: cash spends, gift income,
    CRED cashback contributions, MobiKwik wallet contributions, etc.
    """
    db: Session = SessionLocal()
    try:
        existing = (
            db.query(Account)
            .filter(Account.name == DEFAULT_CASH_ACCOUNT_NAME)
            .first()
        )
        if existing:
            return existing.id
        account = Account(
            name=DEFAULT_CASH_ACCOUNT_NAME,
            type="cash",
            institution=None,
            account_mask=None,
            currency="INR",
            opening_balance=0.0,
            is_active=1,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account.id
    finally:
        db.close()


def ensure_default_accounts() -> dict:
    """Ensure both default accounts exist. Returns {'hdfc': id, 'cash': id}.

    This is the single entry point app startup should call.
    """
    return {
        "hdfc": ensure_default_account(),
        "cash": ensure_default_cash_account(),
    }


def get_default_account_id() -> int:
    """Return the id of the default HDFC account. Creates it if missing."""
    return ensure_default_account()


def get_default_cash_account_id() -> int:
    """Return the id of the default Cash account. Creates it if missing."""
    return ensure_default_cash_account()

def run_migrations(db_session_factory=None) -> None:
    """Idempotent schema migrations. Safe to run on every startup."""
    from sqlalchemy import text
    db = (db_session_factory or SessionLocal)()
    try:
        # Migration: add generated_description to canonical_events
        try:
            db.execute(text(
                "ALTER TABLE canonical_events ADD COLUMN generated_description TEXT"
            ))
            db.commit()
            print("[migration] Added generated_description column.")
        except Exception:
            db.rollback()  # column already exists, safe to ignore

        # Migration: add user_id to category_rules if missing
        try:
            db.execute(text(
                "ALTER TABLE category_rules ADD COLUMN user_id INTEGER REFERENCES users(id)"
            ))
            db.commit()
            print("[migration] Added user_id to category_rules.")
        except Exception:
            db.rollback()
    finally:
        db.close()
