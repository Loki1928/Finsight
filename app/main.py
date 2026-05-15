"""FastAPI entrypoint. Wires routers, creates tables on startup."""
from fastapi import FastAPI
from app.db.session import engine, Base
from app.models import models  # noqa: F401 — ensures models register with Base
from app.api import dashboard, uploads, transactions

app = FastAPI(title="Finsight", version="0.1.0")


@app.on_event("startup")
def _create_tables():
    """V1 simplified: create tables on startup instead of running Alembic.
    Alembic config will be added before V1.1 / first schema change."""
    Base.metadata.create_all(bind=engine)


app.include_router(dashboard.router)
app.include_router(uploads.router)
app.include_router(transactions.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
