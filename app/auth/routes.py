"""OAuth HTTP routes: login, callback, logout.

Flow:
    1. User hits /auth/login            → server-rendered page with one button.
    2. Button POSTs to /auth/login      → redirects to Google's consent screen.
    3. Google redirects to /auth/callback with an authorization code.
    4. Server exchanges code for tokens, fetches user info, upserts the
       User row, marks the session as logged in, redirects to "/".
    5. /auth/logout clears the session and redirects to /auth/login.

Public routes (no auth required): all three handlers in this file plus /health.
Everything else is protected — see dependencies.py for the require_user check.
"""
from datetime import datetime
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.allowlist import is_allowed
from app.auth.oauth import oauth
from app.auth.session import current_user_id, log_in, log_out
from app.db.session import SessionLocal
from app.models.models import User

templates = Jinja2Templates(directory="app/templates")


# OAUTH_REDIRECT_URI lets us pin the callback URL to a known-good value
# regardless of what the request thinks its own hostname is. Needed in
# Codespaces (where the public hostname doesn't reach the server cleanly)
# and harmless in production (Railway sets this env var to the Railway URL).
# If unset, fall back to deriving from the request — fine for plain localhost dev.
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")


router = APIRouter(prefix="/auth", tags=["auth"])


def get_db():
    """Per-request DB session. Same shape used elsewhere in the project."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


LOGIN_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sign in — Finsight</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen flex items-center justify-center">
  <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8 max-w-md w-full">
    <h1 class="text-2xl font-semibold text-gray-900 mb-1">Finsight</h1>
    <p class="text-sm text-gray-500 mb-6">Sign in to continue.</p>
    <form method="post" action="/auth/login">
      <button type="submit"
              class="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5
                     bg-white border border-gray-300 rounded-md text-sm font-medium
                     text-gray-700 hover:bg-gray-50 transition">
        <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
          <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
          <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
          <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
          <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
        </svg>
        Sign in with Google
      </button>
    </form>
    <p class="text-xs text-gray-400 mt-6 text-center">
      We only see your name, email, and profile picture.
    </p>
  </div>
</body>
</html>"""


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """If already logged in, bounce straight to the dashboard.
    Otherwise show the Sign in with Google page."""
    if current_user_id(request) is not None:
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(LOGIN_PAGE_HTML)


@router.post("/login")
async def login_start(request: Request):
    """POST /auth/login -> redirect to Google's consent screen.
    Authlib generates the state parameter and stashes it in the session
    so /auth/callback can verify it."""
    redirect_uri = OAUTH_REDIRECT_URI or str(request.url_for("auth_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    """Google redirects here with ?code=... after the user consents.
    Exchange code for tokens, upsert User, mark session as logged in."""
    token = await oauth.google.authorize_access_token(request)

    # ID token claims include the fields we want: sub, email, name, picture.
    # authorize_access_token already verifies the JWT signature against
    # Google's JWKS, so we trust the claims dict.
    claims = token.get("userinfo") or {}
    google_sub = claims.get("sub")
    email = claims.get("email")
    full_name = claims.get("name")
    picture_url = claims.get("picture")

    if not google_sub or not email:
        # Should never happen with the openid+email scopes, but if Google
        # ever returns a malformed response, fail cleanly instead of writing
        # a half-broken User row.
        return RedirectResponse("/auth/login?error=missing_claims", status_code=302)

    if not is_allowed(email):
        # Not on the tester allowlist — clear any partial OAuth state and
        # show the rejection page. No User row is created.
        request.session.clear()
        return templates.TemplateResponse(
            "not_invited.html", {"request": request}, status_code=403
        )

    user = db.query(User).filter(User.google_sub == google_sub).first()
    if user is None:
        user = User(
            google_sub=google_sub,
            email=email,
            full_name=full_name,
            picture_url=picture_url,
        )
        db.add(user)
    else:
        # Returning user: refresh their profile info in case it changed
        # on Google's side (new email, new name, new picture).
        user.email = email
        user.full_name = full_name
        user.picture_url = picture_url
        user.last_login = datetime.utcnow()

    db.commit()
    db.refresh(user)
    log_in(request, user.id)
    if not user.consent_given:
        return RedirectResponse("/auth/consent", status_code=302)
    return RedirectResponse("/", status_code=302)

@router.get("/logout")
async def logout(request: Request):
    """Clear the session and bounce to the login page."""
    log_out(request)
    return RedirectResponse("/auth/login", status_code=302)

@router.get("/consent", response_class=HTMLResponse)
async def consent_page(request: Request):
    """Show the consent/ToS page to new users."""
    if current_user_id(request) is None:
        return RedirectResponse("/auth/login", status_code=302)
    return templates.TemplateResponse("consent.html", {"request": request})


@router.post("/consent")
async def consent_submit(request: Request, db: Session = Depends(get_db)):
    """User accepted ToS — mark consent_given and go to dashboard."""
    uid = current_user_id(request)
    if uid is None:
        return RedirectResponse("/auth/login", status_code=302)
    user = db.query(User).filter(User.id == uid).first()
    if user:
        user.consent_given = True
        db.commit()
    return RedirectResponse("/", status_code=302)