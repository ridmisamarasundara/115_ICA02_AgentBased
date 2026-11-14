from io import BytesIO

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.agent_client import ask
from app.agents.booking_agent import refund_percent
from app.agents.messages import Performative as P
from app.database import get_db
from app.deps import flash, require_user
from app.models import Booking, Event, Payment, Ticket, TicketCategory
from app.models._util import utcnow
from app.security import verify_csrf
from app.templating import templates

router = APIRouter()


def _booking_view(db, b):
    ev = db.get(Event, b.event_id)
    cat = db.get(TicketCategory, b.category_id)
    now = utcnow()
    can_cancel = b.status == "confirmed" and ev.start_time > now
    pct = refund_percent(ev.start_time, now) if can_cancel else None
    return {"booking": b, "event": ev, "category": cat.name if cat else "", "can_cancel": can_cancel,
            "refund_percent": pct, "refund_now": round(float(b.total_amount) * pct / 100, 2) if can_cancel else 0}


@router.get("/bookings")
def my_bookings(request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    rows = db.query(Booking).filter_by(user_id=user.id).order_by(Booking.created_at.desc(), Booking.id.desc()).all()
    return templates.TemplateResponse(request, "bookings/list.html", {"items": [_booking_view(db, b) for b in rows]})


@router.get("/bookings/{booking_id}")
def booking_detail(booking_id: int, request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    b = db.get(Booking, booking_id)
    if b is None or b.user_id != user.id:
        raise HTTPException(404, "Booking not found")
    tickets = db.query(Ticket).filter_by(booking_id=b.id).order_by(Ticket.id).all()
    payment = db.query(Payment).filter_by(booking_id=b.id).first()
    return templates.TemplateResponse(request, "bookings/detail.html", {
        **_booking_view(db, b), "tickets": tickets, "payment": payment})


@router.post("/bookings/{booking_id}/cancel", dependencies=[Depends(verify_csrf)])
def cancel_booking(booking_id: int, request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    reply = ask(db, "BookingAgent", "cancel", sender=f"User #{user.id}", booking_id=booking_id, user_id=user.id)
    if reply.performative == P.AGREE:
        flash(request, f"Booking cancelled. Refund: Rs. {reply.content['refund']:,.2f} "
                       f"({reply.content['refund_percent']}% under the refund policy).", "success")
    else:
        flash(request, reply.content.get("reason", "The booking could not be cancelled"), "danger")
    return RedirectResponse("/bookings", status_code=303)


@router.get("/tickets/{code}/qr.png")
def ticket_qr(code: str, user=Depends(require_user), db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter_by(code=code).first()
    booking = db.get(Booking, ticket.booking_id) if ticket else None
    if booking is None or booking.user_id != user.id:
        raise HTTPException(404, "Ticket not found")
    buf = BytesIO()
    qrcode.make(code, box_size=8, border=2).save(buf)
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, no-store"})
