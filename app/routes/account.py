from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import Booking, HireRequest, Notification
from app.templating import templates

router = APIRouter()


@router.get("/notifications")
def notifications(request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    rows = (db.query(Notification).filter_by(user_id=user.id)
            .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(50).all())
    items = [{"message": n.message, "created_at": n.created_at, "is_new": not n.is_read} for n in rows]
    for n in rows:
        n.is_read = True
    db.commit()
    return templates.TemplateResponse(request, "notifications.html", {"items": items})


@router.get("/profile")
def profile(request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    counts = {"bookings": db.query(Booking).filter_by(user_id=user.id, status="confirmed").count(),
              "hires": db.query(HireRequest).filter_by(user_id=user.id).count()}
    return templates.TemplateResponse(request, "profile.html", {"counts": counts})
