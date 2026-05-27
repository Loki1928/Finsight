"""Authlib OAuth client configuration.

We register a single provider ("google") that handles the full OIDC flow:
discovery doc fetch, authorization URL generation, token exchange, and
ID token validation. Routes in routes.py call oauth.google.authorize_redirect(...)
and oauth.google.authorize_access_token(...) — Authlib does the rest.

Environment variables (loaded from .env in dev, from Railway in production):
    GOOGLE_CLIENT_ID      — OAuth client ID from Google Cloud Console
    GOOGLE_CLIENT_SECRET  — OAuth client secret from Google Cloud Console
"""
import os

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv


# Load .env in development. In Railway production the env vars are already
# set by the platform and load_dotenv silently does nothing useful (no .env
# file exists in the container), which is the desired behavior.
load_dotenv()


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    raise RuntimeError(
        "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set. "
        "Check your .env file (Codespaces) or Railway Variables (production)."
    )


oauth = OAuth()

oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        # openid + email + profile gives us: sub, email, name, picture.
        # That's everything the User model needs.
        "scope": "openid email profile",
    },
)