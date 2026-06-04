"""SQLAlchemy session and engine setup.

Uses Postgres (e.g. Neon) when DATABASE_URL is set; otherwise falls back to
local SQLite with WAL mode for development in Codespaces.
"""
import os
from pathlib import Path

from dotenv import load_dotenv                          # <-- ADD THIS LINE
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()     

DATABASE_URL = os.environ.get("DATABASE_URL")

# Filesystem location for uploaded files (and the SQLite DB in local dev).
# Defined at top level so it works regardless of which database is in use.
DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent.parent / "data")))
DATA_DIR.mkdir(exist_ok=True)                                      # <-- ADD THIS LINE

if DATABASE_URL:
    # --- Postgres (Neon) ---
    # Some providers emit the old "postgres://" scheme; SQLAlchemy needs "postgresql://".
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Neon scales to zero; re-check stale connections before use
    )
else:
    # --- SQLite (local dev fallback) ---
    DB_PATH = DATA_DIR / "finsight.db"
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_wal(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()