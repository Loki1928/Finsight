"""FastAPI entrypoint. Wires routers, creates tables on startup."""
import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.db.session import engine, Base
from app.models import models  # noqa: F401 — ensures models register with Base
from app.api import dashboard, uploads, transactions
from app.auth import routes as auth_routes
from app.auth.dependencies import _RedirectToLogin
from app.db.bootstrap import ensure_default_accounts

app = FastAPI(title="Finsight", version="0.1.0")

# Sign session cookies with SESSION_SECRET_KEY. The cookie is opaque to the
# browser (the payload is base64-encoded but the signature is what stops
# tampering). Sessions last 30 days by default; testers stay logged in across
# the full testing window without re-auth, which matches the bar we set.
_SESSION_SECRET = os.getenv("SESSION_SECRET_KEY")
if not _SESSION_SECRET:
    raise RuntimeError(
        "SESSION_SECRET_KEY must be set in .env (Codespaces) or Railway Variables."
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
    session_cookie="finsight_session",
    max_age=60 * 60 * 24 * 30,   # 30 days
    same_site="lax",              # required so the OAuth callback brings the cookie back
    https_only=False,             # flipped to True once we're on Railway-only with TLS
)


@app.exception_handler(_RedirectToLogin)
async def _redirect_to_login_handler(request: Request, exc: _RedirectToLogin):
    """Turn the dependency's short-circuit exception into a 302 redirect."""
    return RedirectResponse("/auth/login", status_code=302)


app.include_router(auth_routes.router)


@app.on_event("startup")
def _startup():
    """V1 simplified: create tables on startup instead of running Alembic.
    Also bootstrap default accounts (HDFC + Cash) so uploads and manual
    entries have accounts to bind to.
    Inline migrations: add columns that may not exist in older DBs."""
    Base.metadata.create_all(bind=engine)
    ensure_default_accounts()
    # Inline migration: add user_id to tables that predate P1.3
    import sqlite3
    from app.db.session import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    for table in ["canonical_events", "uploads", "raw_transactions"]:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        except sqlite3.OperationalError:
            pass  # column already exists — safe to ignore
    conn.commit()
    conn.close()

    # Patch any rows with NULL user_id to user_id=1 (the first user)
    for table in ["canonical_events", "uploads", "raw_transactions"]:
        cur.execute(f"UPDATE {table} SET user_id=1 WHERE user_id IS NULL")
    conn.commit()


app.include_router(dashboard.router)
app.include_router(uploads.router)
app.include_router(transactions.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}