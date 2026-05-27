"""FastAPI dependencies for protecting routes.

Usage:
    @router.get("/")
    def dashboard(user: User = Depends(require_user)):
        # user is guaranteed to be a logged-in User row
        ...

If the request has no valid session, require_user raises a redirect to
/auth/login. The dashboard handler never runs in the unauthenticated case.
"""
from fastapi import Depends, Request, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.session import current_user
from app.db.session import SessionLocal
from app.models.models import User


def get_db():
    """Per-request DB session. Duplicated from routes.py so dependencies.py
    has no import dependency on the routes module — keeps the import graph clean."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class _RedirectToLogin(HTTPException):
    """Sentinel exception that the exception handler in main.py turns into
    a 302 redirect to /auth/login. We use an exception (rather than just
    returning a RedirectResponse) because FastAPI dependencies can only
    short-circuit the request by raising, not by returning."""

    def __init__(self):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_logged_in")


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the session to a User row, or raise _RedirectToLogin.

    Routes that need a logged-in user declare this dependency. The handler
    body sees a fully populated User instance and can use it directly:
        user.id, user.email, user.full_name, user.picture_url
    """
    user = current_user(request, db)
    if user is None:
        raise _RedirectToLogin()
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Like require_user but returns None instead of redirecting.

    Use for routes that render different content for logged-in vs anonymous
    users without forcing a redirect — e.g. a future public landing page.
    Not used yet, but it's the kind of thing you reach for once around it
    enough times that adding it preemptively saves you later."""
    return current_user(request, db)