from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.database import SessionLocal
from app.models import Notification, User
from app.security import get_csrf_token

BASE_DIR = Path(__file__).resolve().parent


def template_context(request: Request) -> dict:
    """Variables available in every template."""
    user, unread = None, 0
    uid = request.session.get("user_id")
    if uid:
        with SessionLocal() as db:
            user = db.get(User, uid)
            if user:
                unread = db.query(Notification).filter_by(user_id=uid, is_read=False).count()
    return {
        "current_user": user,
        "unread_count": unread,
        "csrf_token": get_csrf_token(request),
        "flashes": request.session.pop("flash", []),
        "current_path": request.url.path,
    }


templates = Jinja2Templates(directory=BASE_DIR / "templates", context_processors=[template_context])
templates.env.filters["money"] = lambda v: f"Rs. {float(v or 0):,.2f}"
templates.env.filters["dt"] = lambda v: v.strftime("%a %d %b %Y, %H:%M") if v else ""


def _short_dt(v):
    """Oct 26, 7:00 PM"""
    if not v:
        return ""
    return f"{v.strftime('%b')} {v.day}, {v.hour % 12 or 12}:{v.minute:02d} {'AM' if v.hour < 12 else 'PM'}"


def _full_dt(v):
    """Oct 26, 2026 \u2022 7:00 PM"""
    if not v:
        return ""
    return f"{v.strftime('%b')} {v.day}, {v.year} \u2022 {v.hour % 12 or 12}:{v.minute:02d} {'AM' if v.hour < 12 else 'PM'}"


templates.env.filters["short_dt"] = _short_dt
templates.env.filters["full_dt"] = _full_dt
