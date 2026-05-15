"""Idempotent bootstrap: ensures a default HDFC account row exists.

Runs at app startup. Safe to call repeatedly — checks for existence first.
"""
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.models import Account


DEFAULT_HDFC_ACCOUNT_NAME = "HDFC Savings (default)"


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


def get_default_account_id() -> int:
    """Return the id of the default HDFC account. Creates it if missing."""
    return ensure_default_account()
