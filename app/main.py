"""FastAPI entrypoint. Wires routers, creates tables on startup."""
import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.db.session import engine, Base
from app.models import models  # noqa: F401 — ensures models register with Base
from app.api import dashboard, uploads, transactions, feedback, account, categories, rules
from app.auth import routes as auth_routes
from app.auth.dependencies import _RedirectToLogin
from app.db.bootstrap import run_migrations,  ensure_default_accounts


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
    https_only=True,              # Render provides TLS
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

    Inline idempotent migrations add columns that predate P1.3. Works on both
    SQLite (local dev) and Postgres (Neon) by branching on the engine dialect.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    Base.metadata.create_all(bind=engine)
    ensure_default_accounts()
    run_migrations()

    is_postgres = engine.dialect.name == "postgresql"
    tables = ["canonical_events", "uploads", "raw_transactions"]

    # Phase 1: ensure user_id column exists. Each ALTER runs in its own
    # transaction so a caught "already exists" on SQLite can't poison the rest.
    for table in tables:
        try:
            with engine.begin() as conn:
                if is_postgres:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id INTEGER"
                    ))
                else:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"
                    ))
        except OperationalError:
            pass  # SQLite: column already exists — safe to ignore

    # Phase 2: patch any legacy rows with NULL user_id to the first user.
    with engine.begin() as conn:
        for table in tables:
            conn.execute(text(f"UPDATE {table} SET user_id=1 WHERE user_id IS NULL"))

    # Phase 3: ensure consent_given column exists on users table.
    try:
        with engine.begin() as conn:
            if is_postgres:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_given BOOLEAN DEFAULT FALSE"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN consent_given BOOLEAN DEFAULT 0"
                ))
    except OperationalError:
        pass  # SQLite: column already exists


app.include_router(dashboard.router)
app.include_router(uploads.router)
app.include_router(transactions.router)
app.include_router(feedback.router)
app.include_router(account.router)
app.include_router(categories.router)
app.include_router(rules.router)


@app.get("/terms")
async def terms(request: Request):
    from fastapi.responses import HTMLResponse
    from fastapi.templating import Jinja2Templates
    t = Jinja2Templates(directory="app/templates")
    return t.TemplateResponse("terms.html", {"request": request})


@app.get("/privacy")
async def privacy_page(request: Request):
    from fastapi.responses import HTMLResponse
    from fastapi.templating import Jinja2Templates
    t = Jinja2Templates(directory="app/templates")
    return t.TemplateResponse("privacy.html", {"request": request})


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}