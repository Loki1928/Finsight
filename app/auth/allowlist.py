import os

def allowed_emails() -> set[str]:
    raw = os.getenv("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}

def is_allowed(email: str | None) -> bool:
    if not email:
        return False
    # Empty allowlist = deny all (fail closed), not open to everyone.
    return email.strip().lower() in allowed_emails()