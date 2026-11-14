import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


class LoginRequired(Exception):
    def __init__(self, next_url: str = "/"):
        self.next_url = next_url


def current_user(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("user_id")
    return db.get(User, uid) if uid else None


def require_user(request: Request, user=Depends(current_user)):
    if user is None:
        raise LoginRequired(request.url.path)
    return user


def require_role(*roles: str):
    """Use as Depends(require_role('admin')). Anonymous -> login page, wrong role -> 403."""
    def dependency(user=Depends(require_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to open this page.")
        return user
    return dependency


def login_user(request: Request, user) -> None:
    request.session.clear()                       # new session on login (prevents session fixation)
    request.session["user_id"] = user.id
    request.session["csrf"] = secrets.token_urlsafe(32)


def flash(request: Request, message: str, category: str = "info") -> None:
    request.session.setdefault("flash", []).append([category, message])
    request.session["flash"] = request.session["flash"]    # mark the session as modified


def safe_next(url: str | None) -> str | None:
    """Only allow local paths, never other websites (open-redirect protection)."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None
