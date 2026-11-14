from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.agent_client import ask
from app.agents.messages import Performative as P
from app.constants import EVENT_CATEGORIES
from app.database import get_db
from app.deps import current_user, flash, require_user
from app.models import Event, WaitlistEntry
from app.models._util import utcnow
from app.security import verify_csrf
from app.templating import templates

router = APIRouter()


@router.get("/")
def event_list(request: Request, q: str = "", category: str = "", db: Session = Depends(get_db)):
    query = db.query(Event).filter(Event.status == "published", Event.end_time > utcnow())
    q = q.strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Event.title.ilike(like), Event.description.ilike(like)))
    if category in EVENT_CATEGORIES:
        query = query.filter(Event.category == category)
    items = []
    for ev in query.order_by(Event.start_time, Event.id).all():
        cats = ev.categories
        items.append({"event": ev, "venue": ev.venue.name,
                      "from_price": min((c.price for c in cats), default=0),
                      "left": sum(max(c.quantity - c.sold, 0) for c in cats)})
    return templates.TemplateResponse(request, "events/list.html", {
        "items": items, "q": q, "category": category, "categories": EVENT_CATEGORIES})


@router.get("/events/{event_id}")
def event_detail(event_id: int, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if ev is None or (ev.status == "draft" and not (user and user.role == "admin")):
        raise HTTPException(404, "Event not found")
    cats = []
    for c in sorted(ev.categories, key=lambda c: c.id):
        db.refresh(c)
        cats.append({"id": c.id, "name": c.name, "price": c.price, "left": max(c.quantity - c.sold, 0)})
    names = {c["id"]: c["name"] for c in cats}

    entries = []
    if user:
        now = utcnow()
        rows = db.query(WaitlistEntry).filter(WaitlistEntry.user_id == user.id, WaitlistEntry.event_id == ev.id,
                                              WaitlistEntry.status.in_(["waiting", "held"])).order_by(WaitlistEntry.id).all()
        for e in rows:
            position = db.query(WaitlistEntry).filter(
                WaitlistEntry.category_id == e.category_id, WaitlistEntry.status == "waiting",
                WaitlistEntry.id <= e.id).count()
            seconds = max(int((e.hold_expires_at - now).total_seconds()), 0) if e.hold_expires_at else 0
            entries.append({"id": e.id, "status": e.status, "quantity": e.quantity, "position": position,
                            "category": names.get(e.category_id, ""), "seconds_left": seconds})
    on_sale = ev.status == "published" and ev.start_time > utcnow()
    return templates.TemplateResponse(request, "events/detail.html", {
        "event": ev, "cats": cats, "entries": entries, "on_sale": on_sale,
        "any_left": any(c["left"] > 0 for c in cats)})


@router.post("/events/{event_id}/book", dependencies=[Depends(verify_csrf)])
def book(event_id: int, request: Request, category_id: int = Form(0), quantity: int = Form(1),
         user=Depends(require_user), db: Session = Depends(get_db)):
    reply = ask(db, "BookingAgent", "book", sender=f"User #{user.id}", user_id=user.id,
                event_id=event_id, category_id=category_id, quantity=quantity)
    if reply.performative == P.AGREE:
        flash(request, f"Booking confirmed! Payment reference {reply.content['payment_reference']}.", "success")
        return RedirectResponse(f"/bookings/{reply.content['booking_id']}", status_code=303)
    reason = reply.content.get("reason", "The booking could not be made")
    if reply.content.get("can_join_waitlist"):
        reason += ". You can join the waitlist below."
    flash(request, reason, "danger")
    return RedirectResponse(f"/events/{event_id}", status_code=303)


@router.post("/events/{event_id}/waitlist", dependencies=[Depends(verify_csrf)])
def join_waitlist(event_id: int, request: Request, category_id: int = Form(0), quantity: int = Form(1),
                  user=Depends(require_user), db: Session = Depends(get_db)):
    reply = ask(db, "WaitlistAgent", "join", sender=f"User #{user.id}", user_id=user.id,
                event_id=event_id, category_id=category_id, quantity=quantity)
    if reply.performative == P.AGREE:
        flash(request, f"You are #{reply.content['position']} on the waitlist. We will hold seats for you "
                       "when they become free.", "success")
    else:
        flash(request, reply.content.get("reason", "Could not join the waitlist"), "danger")
    return RedirectResponse(f"/events/{event_id}", status_code=303)


def _entry_or_404(db, entry_id):
    entry = db.get(WaitlistEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Waitlist entry not found")
    return entry


@router.post("/waitlist/{entry_id}/claim", dependencies=[Depends(verify_csrf)])
def claim_hold(entry_id: int, request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    entry = _entry_or_404(db, entry_id)
    event_id = entry.event_id
    reply = ask(db, "WaitlistAgent", "claim", sender=f"User #{user.id}", entry_id=entry_id, user_id=user.id)
    if reply.performative == P.AGREE:
        flash(request, "Your held seats are now booked. Enjoy the event!", "success")
        return RedirectResponse(f"/bookings/{reply.content['booking_id']}", status_code=303)
    flash(request, reply.content.get("reason", "Could not claim the seats"), "danger")
    return RedirectResponse(f"/events/{event_id}", status_code=303)


@router.post("/waitlist/{entry_id}/leave", dependencies=[Depends(verify_csrf)])
def leave_waitlist(entry_id: int, request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    entry = _entry_or_404(db, entry_id)
    event_id = entry.event_id
    reply = ask(db, "WaitlistAgent", "leave", sender=f"User #{user.id}", entry_id=entry_id, user_id=user.id)
    flash(request, "You left the waitlist." if reply.performative == P.AGREE
          else reply.content.get("reason", "Could not leave the waitlist"),
          "info" if reply.performative == P.AGREE else "danger")
    return RedirectResponse(f"/events/{event_id}", status_code=303)
