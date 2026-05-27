"""Session helpers backed by Starlette's SessionMiddleware (signed cookies).

The SessionMiddleware itself is installed in app/main.py; it signs and
serializes a small dict stored in the cookie named "session". These helpers
read/write that dict via request.session.

We deliberately store only the user_id in the session, never email or name.
Display values (name, avatar) are fetched fresh from the User row per request,
so a user's profile updates take effect immediately on next request.
"""
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.models import User


SESSION_USER_KEY = "user_id"


def log_in(request: Request, user_id: int) -> None:
    """Mark the request's session as logged in for the given user_id."""
    request.session[SESSION_USER_KEY] = user_id


def log_out(request: Request) -> None:
    """Clear the session. The cookie itself remains but holds no user."""
    request.session.pop(SESSION_USER_KEY, None)


def current_user_id(request: Request) -> Optional[int]:
    """Return the user_id from the session, or None if not logged in."""
    return request.session.get(SESSION_USER_KEY)


def current_user(request: Request, db: Session) -> Optional[User]:
    """Resolve the session's user_id to a User row. None if unauthenticated
    or if the session points at a user that no longer exists (e.g. deleted)."""
    user_id = current_user_id(request)
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()