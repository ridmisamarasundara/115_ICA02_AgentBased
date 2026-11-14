"""BookingAgent - goal: sell tickets fairly without overselling.

DECISION RULES (copy into the report)
Booking (action: book)
  B1  1 to 6 tickets per request, else REFUSE.
  B2  Event must exist and be published, else REFUSE.
  B3  Sales close when the event starts, else REFUSE.
  B4  The ticket category must belong to the event, else REFUSE.
  B5  One user may hold at most 10 tickets per event, else REFUSE.
  B6  Seat allocation is ONE atomic statement:
        UPDATE ticket_categories SET sold = sold + :n WHERE id = :id AND sold + :n <= quantity
      0 rows updated -> REFUSE ("only N left", can_join_waitlist). The database also has a
      CHECK (sold <= quantity) constraint as a last line of defence.
  B7  Payment is simulated: a reference "PAY-XXXXXXXX" is stored, no card data.
  B8  Tickets are issued by TicketAgent; if that fails the seats are released (compensation).
  B9  A booking marked from_hold skips B6: WaitlistAgent already reserved those seats for the user.
Cancellation (action: cancel)
  R1  Only the owner can cancel, and only a confirmed booking.
  R2  Not allowed once the event has started, or if a ticket was already used.
  R3  Refund policy: more than 7 days before start = 100%, 48 hours to 7 days = 50%,
      under 48 hours = 0%.
  R4  Seats are released and WaitlistAgent is told (INFORM seats_freed).
Event cancellation (action: cancel_event)
  X1  Only a published event that has not ended can be cancelled.
  X2  Every confirmed booking is refunded 100%, tickets cancelled, users notified.
STATE: bookings_accepted, bookings_refused, tickets_sold, cancellations, refunds_total,
       checkins_seen (from TicketAgent)
"""
import secrets
from datetime import timedelta

from sqlalchemy import update, func

from app.agents.base import BaseAgent
from app.agents.messages import Performative as P
from app.models import Event, TicketCategory, Booking, Payment
from app.models._util import utcnow

MAX_PER_REQUEST = 6
MAX_PER_USER_PER_EVENT = 10


def refund_percent(start, now) -> int:
    delta = start - now
    if delta > timedelta(days=7):
        return 100
    if delta >= timedelta(hours=48):
        return 50
    return 0


class BookingAgent(BaseAgent):
    name = "BookingAgent"

    def _bump(self, db, key, n=1):
        self.set_state(db, key, self.get_state(db, key, 0) + n)

    def _release(self, db, category_id, qty):
        db.execute(update(TicketCategory)
                   .where(TicketCategory.id == category_id, TicketCategory.sold >= qty)
                   .values(sold=TicketCategory.sold - qty)
                   .execution_options(synchronize_session=False))
        db.expire_all()

    def _refuse(self, msg, db, reason, counter="bookings_refused", **extra):
        self._bump(db, counter)
        return msg.reply(P.REFUSE, {"reason": reason, **extra})

    # ------------------------------------------------------------ booking
    def on_book(self, msg, db):
        c = msg.content
        try:
            user_id, event_id = int(c["user_id"]), int(c["event_id"])
            category_id, qty = int(c["category_id"]), int(c["quantity"])
        except (KeyError, ValueError, TypeError):
            return msg.reply(P.FAILURE, {"reason": "user_id, event_id, category_id and quantity are required"})

        if not 1 <= qty <= MAX_PER_REQUEST:                                        # B1
            return self._refuse(msg, db, f"You can book 1 to {MAX_PER_REQUEST} tickets per request")
        event = db.get(Event, event_id)
        if event is None or event.status != "published":                          # B2
            return self._refuse(msg, db, "This event is not on sale")
        if event.start_time <= utcnow():                                           # B3
            return self._refuse(msg, db, "Ticket sales are closed because the event has started")
        cat = db.get(TicketCategory, category_id)
        if cat is None or cat.event_id != event.id:                                # B4
            return self._refuse(msg, db, "Ticket category does not belong to this event")
        already = db.query(func.coalesce(func.sum(Booking.quantity), 0)).filter(
            Booking.user_id == user_id, Booking.event_id == event.id,
            Booking.status == "confirmed").scalar()
        if already + qty > MAX_PER_USER_PER_EVENT:                                 # B5
            return self._refuse(msg, db, f"Limit is {MAX_PER_USER_PER_EVENT} tickets per person for one event "
                                         f"(you already hold {already})")

        from_hold = bool(c.get("from_hold"))     # B9: seats already reserved for this user by WaitlistAgent
        if not from_hold:
            res = db.execute(update(TicketCategory).where(                         # B6
                TicketCategory.id == cat.id, TicketCategory.sold + qty <= TicketCategory.quantity)
                .values(sold=TicketCategory.sold + qty).execution_options(synchronize_session=False))
            db.refresh(cat)
            if res.rowcount == 0:
                left = max(cat.quantity - cat.sold, 0)
                return self._refuse(msg, db, f"Only {left} ticket(s) left in '{cat.name}'",
                                    tickets_left=left, can_join_waitlist=True,
                                    event_id=event.id, category_id=cat.id)

        total = round(float(cat.price) * qty, 2)
        booking = Booking(user_id=user_id, event_id=event.id, category_id=cat.id, quantity=qty,
                          total_amount=total, status="confirmed")
        db.add(booking)
        db.flush()
        payment = Payment(booking_id=booking.id, reference="PAY-" + secrets.token_hex(4).upper(),   # B7
                          amount=total, status="paid")
        db.add(payment)
        db.flush()

        issued = self.send("TicketAgent", P.REQUEST,                                # B8
                           {"action": "issue", "booking_id": booking.id, "event_id": event.id, "quantity": qty},
                           db, msg.conversation_id)
        if issued is None or issued.performative != P.AGREE:
            db.delete(payment)
            db.delete(booking)
            db.flush()
            if not from_hold:                  # held seats stay with WaitlistAgent
                self._release(db, cat.id, qty)
            reason = issued.content.get("reason", "unknown") if issued else "no answer"
            return msg.reply(P.FAILURE, {"reason": f"Tickets could not be issued, seats released ({reason})"})

        self._bump(db, "bookings_accepted")
        self._bump(db, "tickets_sold", qty)
        self.broadcast("booking_confirmed", {"user_id": user_id, "booking_id": booking.id,
                                             "quantity": qty, "event_title": event.title},
                       db, msg.conversation_id)
        return msg.reply(P.AGREE, {"booking_id": booking.id, "payment_reference": payment.reference,
                                   "total": total, "quantity": qty, "ticket_codes": issued.content["codes"]})

    # ------------------------------------------------------------ cancellation
    def on_cancel(self, msg, db):
        c = msg.content
        booking = db.get(Booking, int(c.get("booking_id", 0)))
        if booking is None:
            return msg.reply(P.FAILURE, {"reason": "Booking not found"})
        if c.get("user_id") is not None and booking.user_id != int(c["user_id"]):  # R1
            return self._refuse(msg, db, "This is not your booking", counter="cancel_refused")
        if booking.status != "confirmed":
            return self._refuse(msg, db, f"Booking is already {booking.status}", counter="cancel_refused")
        event = db.get(Event, booking.event_id)
        now = utcnow()
        if event.start_time <= now:                                                # R2
            return self._refuse(msg, db, "The event has already started, so the booking cannot be cancelled",
                                counter="cancel_refused")
        tk = self.send("TicketAgent", P.REQUEST, {"action": "cancel_tickets", "booking_id": booking.id},
                       db, msg.conversation_id)
        if tk is None or tk.performative != P.AGREE:
            return self._refuse(msg, db, (tk.content.get("reason") if tk else "Tickets could not be cancelled"),
                                counter="cancel_refused")

        pct = refund_percent(event.start_time, now)                                # R3
        refund = round(float(booking.total_amount) * pct / 100, 2)
        booking.status, booking.refund_amount, booking.cancelled_at = "cancelled", refund, now
        if booking.payment is not None and pct > 0:
            booking.payment.status = "refunded" if pct == 100 else "partially_refunded"
        db.flush()
        self._release(db, booking.category_id, booking.quantity)                   # R4
        self.send("WaitlistAgent", P.INFORM,
                  {"action": "seats_freed", "event_id": event.id, "category_id": booking.category_id,
                   "quantity": booking.quantity}, db, msg.conversation_id)
        self.broadcast("booking_cancelled", {"user_id": booking.user_id, "booking_id": booking.id,
                                             "refund": f"{refund:,.2f}"}, db, msg.conversation_id)
        self._bump(db, "cancellations")
        self.set_state(db, "refunds_total", round(self.get_state(db, "refunds_total", 0) + refund, 2))
        return msg.reply(P.AGREE, {"refund": refund, "refund_percent": pct,
                                   "reason": f"Refund policy: {pct}% refunded"})

    def on_cancel_event(self, msg, db):
        event = db.get(Event, int(msg.content.get("event_id", 0)))
        if event is None:
            return msg.reply(P.FAILURE, {"reason": "Event not found"})
        if event.status != "published":                                            # X1
            return msg.reply(P.REFUSE, {"reason": "Only published events can be cancelled"})
        if event.end_time <= utcnow():
            return msg.reply(P.REFUSE, {"reason": "The event has already ended"})
        event.status = "cancelled"
        total, count = 0.0, 0
        for b in db.query(Booking).filter_by(event_id=event.id, status="confirmed").all():   # X2
            self.send("TicketAgent", P.REQUEST,
                      {"action": "cancel_tickets", "booking_id": b.id, "force": True}, db, msg.conversation_id)
            b.status, b.refund_amount, b.cancelled_at = "cancelled", b.total_amount, utcnow()
            if b.payment is not None:
                b.payment.status = "refunded"
            total += float(b.total_amount)
            count += 1
            self.broadcast("event_cancelled", {"user_id": b.user_id, "event_title": event.title,
                                               "refund": f"{float(b.total_amount):,.2f}"},
                           db, msg.conversation_id)
        db.flush()
        self.send("WaitlistAgent", P.INFORM, {"action": "event_cancelled", "event_id": event.id},
                  db, msg.conversation_id)
        self._bump(db, "events_cancelled")
        self.set_state(db, "refunds_total", round(self.get_state(db, "refunds_total", 0) + total, 2))
        return msg.reply(P.AGREE, {"bookings_refunded": count, "total_refunded": round(total, 2)})

    # ------------------------------------------------------------ messages from TicketAgent
    def on_ticket_admitted(self, msg, db):
        self._bump(db, "checkins_seen")
        return None
