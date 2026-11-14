import secrets

from fastapi import HTTPException, Request
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(password, password_hash)
    except Exception:
        return False


# ---- CSRF: one random token per session, required on every state-changing request ----
def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


async def verify_csrf(request: Request):
    """Dependency for POST routes. Accepts the form field 'csrf_token' or the X-CSRF-Token header."""
    form = await request.form()
    sent = str(form.get("csrf_token") or request.headers.get("x-csrf-token", ""))
    expected = request.session.get("csrf", "")
    if not expected or not secrets.compare_digest(sent, expected):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token. Please reload the page and try again.")
