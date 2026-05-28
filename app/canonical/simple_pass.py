"""Simple 1:1 canonical pass — every raw row becomes its own canonical event.

This is a deliberate V1 simplification. Real reconciliation (which detects
that the same payment from a wallet export and a bank statement is one
event, not two) is Step 7. For now we just need transactions to show up
on the dashboard.
"""
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.models import RawTransaction, CanonicalEvent
from app.canonical.categorize import categorize_event


def materialize_canonical(db: Session, upload_id: int, user_id: int) -> int:
    """Create a CanonicalEvent for every RawTransaction from this upload
    that doesn't already have one. Returns the number created."""
    rows = (
        db.query(RawTransaction)
        .filter(RawTransaction.upload_id == upload_id)
        .filter(RawTransaction.canonical_event_id.is_(None))
        .all()
    )
    created = 0
    for r in rows:
        event = CanonicalEvent(
            event_date=r.txn_date,
            event_time=r.txn_time,
            amount=r.amount,
            direction=r.direction,
            primary_account_id=r.account_id,
            merchant_raw=r.description,
            merchant_normalized=None,  # set in Step 8 (categorization)
            category=None,
            payment_method=None,
            source_app=None,
            confidence_score=1.0,
            reconciliation_level=0,  # not reconciled, just materialized
            reconciliation_evidence=None,
            is_user_edited=0,
            user_id=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        categorize_event(event)
        db.add(event)
        db.flush()  # get event.id
        r.canonical_event_id = event.id
        created += 1
    db.commit()
    return created
