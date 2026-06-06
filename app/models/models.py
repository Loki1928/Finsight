"""ORM models: the three-layer schema (raw -> reconciliation -> canonical)
plus supporting tables (accounts, uploads, category_rules, audit_log).
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Time,
    ForeignKey, Text, Index,
)
from app.db.session import Base


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # bank | credit_card | wallet | cash
    institution = Column(String)
    account_mask = Column(String)
    currency = Column(String, nullable=False, default="INR")
    opening_balance = Column(Float, default=0.0)
    opening_date = Column(Date)
    credit_limit = Column(Float)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    consent_given = Column(Boolean, default=False)


class Upload(Base):
    __tablename__ = "uploads"
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, unique=True)
    source_type = Column(String, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    rows_parsed = Column(Integer, default=0)
    rows_skipped = Column(Integer, default=0)
    parser_version = Column(String)
    status = Column(String, nullable=False)
    error_log = Column(Text)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))


class RawTransaction(Base):
    __tablename__ = "raw_transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    upload_id = Column(Integer, ForeignKey("uploads.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    source_type = Column(String, nullable=False)
    txn_date = Column(Date, nullable=False)
    value_date = Column(Date)
    txn_time = Column(Time)
    description = Column(Text, nullable=False)
    amount = Column(Float, nullable=False)
    direction = Column(String, nullable=False)
    balance_after = Column(Float)
    reference_id = Column(String)
    upi_id = Column(String)
    raw_row_json = Column(Text, nullable=False)
    canonical_event_id = Column(Integer, ForeignKey("canonical_events.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))


Index("idx_raw_account_date", RawTransaction.account_id, RawTransaction.txn_date)
Index("idx_raw_reference", RawTransaction.reference_id)
Index("idx_raw_canonical", RawTransaction.canonical_event_id)


class CanonicalEvent(Base):
    __tablename__ = "canonical_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_date = Column(Date, nullable=False)
    event_time = Column(Time)
    amount = Column(Float, nullable=False)
    direction = Column(String, nullable=False)
    primary_account_id = Column(Integer, ForeignKey("accounts.id"))
    counter_account_id = Column(Integer, ForeignKey("accounts.id"))
    merchant_raw = Column(Text)
    merchant_normalized = Column(String)
    category = Column(String)
    subcategory = Column(String)
    payment_method = Column(String)
    source_app = Column(String)
    is_transfer = Column(Integer, default=0)
    is_liability_payment = Column(Integer, default=0)
    is_reimbursable = Column(Integer, default=0)
    confidence_score = Column(Float, default=1.0)
    reconciliation_level = Column(Integer)
    reconciliation_evidence = Column(Text)
    notes = Column(Text)
    tags = Column(String)
    is_user_edited = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))


Index("idx_canon_date", CanonicalEvent.event_date)
Index("idx_canon_category", CanonicalEvent.category)
Index("idx_canon_merchant", CanonicalEvent.merchant_normalized)


class CategoryRule(Base):
    __tablename__ = "category_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_field = Column(String, nullable=False)
    match_pattern = Column(String, nullable=False)
    match_type = Column(String, nullable=False)
    category = Column(String, nullable=False)
    subcategory = Column(String)
    priority = Column(Integer, default=100)
    is_active = Column(Integer, default=1)
    times_applied = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer)
    details = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    google_sub = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=False)
    full_name = Column(String)
    picture_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    page = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index("idx_users_google_sub", User.google_sub)
Index("idx_users_email", User.email)