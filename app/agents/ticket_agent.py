"""TicketAgent - goal: admit each ticket exactly once.

DECISION RULES (copy into the report)
Issuing (action: issue)
  T1  Every ticket gets a unique, unguessable code (secrets.token_urlsafe(24)).
Cancelling (action: cancel_tickets)
  T2  Tickets of a booking are cancelled unless one was already used (REFUSE);
      an event cancellation forces cancellation of all tickets.
Door check (action: scan, needs the gate's event_id) - checked in this order:
  S1  unknown code                       -> REFUSE  unknown_ticket
  S2  ticket belongs to another event    -> REFUSE  wrong_event
  S3  ticket cancelled                   -> REFUSE  cancelled
  S4  ticket already used                -> REFUSE  already_used (scan counter increases;
                                            3 or more scans flags the code as suspicious)
  S5  outside check-in time (opens 2 hours before start, closes at event end)
                                         -> REFUSE  outside_checkin_time
  S6  otherwise admit, using one atomic UPDATE ... WHERE status='valid' so two
      simultaneous scans can never both be admitted -> AGREE admit
STATE: tickets_issued, admitted, rejected_<reason> counters, suspicious_codes list
COMMUNICATION: tells BookingAgent (INFORM ticket_admitted) after each admission.
"""
import secrets
from datetime import timedelta

from sqlalchemy import update

from app.agents.base import BaseAgent
from app.agents.messages import Performative as P
from app.models import Ticket, Event, Booking, User, TicketCategory
from app.models._util import utcnow

CHECKIN_OPENS_BEFORE = timedelta(hours=2)
SUSPICIOUS_SCANS = 3


def _fmt(d):
    return d.strftime("%d %b %Y %H:%M") if d else "?"


class TicketAgent(BaseAgent):
    name = "TicketAgent"

    def _bump(self, db, key, n=1):
        self.set_state(db, key, self.get_state(db, key, 0) + n)

    def _new_code(self, db):
        while True:
            code = secrets.token_urlsafe(24)
            if not db.query(Ticket.id).filter_by(code=code).first():
                return code

    # ------------------------------------------------------------ issue / cancel
    def on_issue(self, msg, db):
        c = msg.content
        try:
            booking_id, event_id, qty = int(c["booking_id"]), int(c["event_id"]), int(c["quantity"])
        except (KeyError, ValueError, TypeError):
            return msg.reply(P.FAILURE, {"reason": "booking_id, event_id and quantity are required"})
        if qty < 1:
            return msg.reply(P.FAILURE, {"reason": "quantity must be at least 1"})
        codes = []
        for _ in range(qty):                                                       # T1
            code = self._new_code(db)
            db.add(Ticket(booking_id=booking_id, event_id=event_id, code=code))
            codes.append(code)
        db.flush()
        self._bump(db, "tickets_issued", qty)
        return msg.reply(P.AGREE, {"codes": codes, "count": qty})

    def on_cancel_tickets(self, msg, db):
        c = msg.content
        tickets = db.query(Ticket).filter_by(booking_id=int(c.get("booking_id", 0))).all()
        used = [t for t in tickets if t.status == "used"]
        if used and not c.get("force"):                                            # T2
            return msg.reply(P.REFUSE, {
                "reason": f"{len(used)} ticket(s) already used (checked in), so this booking cannot be cancelled"})
        n = 0
        for t in tickets:
            if t.status != "cancelled":
                t.status = "cancelled"
                n += 1
        db.flush()
        return msg.reply(P.AGREE, {"cancelled": n})

    # ------------------------------------------------------------ door check
    def _reject(self, msg, db, decision, reason, **extra):
        self._bump(db, f"rejected_{decision}")
        return msg.reply(P.REFUSE, {"decision": decision, "reason": reason, **extra})

    def _flag(self, db, code):
        flagged = self.get_state(db, "suspicious_codes", [])
        if code not in flagged:
            self.set_state(db, "suspicious_codes", flagged + [code])

    def _already_used(self, msg, db, ticket):
        db.execute(update(Ticket).where(Ticket.id == ticket.id)
                   .values(scan_count=Ticket.scan_count + 1)
                   .execution_options(synchronize_session=False))
        db.refresh(ticket)
        suspicious = ticket.scan_count >= SUSPICIOUS_SCANS
        if suspicious:
            self._flag(db, ticket.code)
        return self._reject(msg, db, "already_used",
                            f"Ticket already used at {_fmt(ticket.used_at)}",
                            scan_count=ticket.scan_count, suspicious=suspicious)

    def on_scan(self, msg, db):
        c = msg.content
        code = str(c.get("code", "")).strip()
        try:
            gate_event_id = int(c["event_id"])
        except (KeyError, ValueError, TypeError):
            return msg.reply(P.FAILURE, {"reason": "event_id (the event being scanned) is required"})

        ticket = db.query(Ticket).filter_by(code=code).first() if code else None
        if ticket is None:                                                         # S1
            return self._reject(msg, db, "unknown_ticket", "Unknown ticket code")
        if ticket.event_id != gate_event_id:                                       # S2
            other = db.get(Event, ticket.event_id)
            return self._reject(msg, db, "wrong_event",
                                f"This ticket is for a different event ({other.title if other else '?'})")
        if ticket.status == "cancelled":                                           # S3
            return self._reject(msg, db, "cancelled", "Ticket was cancelled (booking or event cancelled)")
        if ticket.status == "used":                                                # S4
            return self._already_used(msg, db, ticket)

        event = db.get(Event, ticket.event_id)
        now = utcnow()
        if now < event.start_time - CHECKIN_OPENS_BEFORE:                          # S5
            return self._reject(msg, db, "outside_checkin_time",
                                f"Check-in opens at {_fmt(event.start_time - CHECKIN_OPENS_BEFORE)}")
        if now > event.end_time:
            return self._reject(msg, db, "outside_checkin_time", "The event has already ended")

        res = db.execute(update(Ticket).where(Ticket.id == ticket.id, Ticket.status == "valid")   # S6
                         .values(status="used", used_at=now, scan_count=Ticket.scan_count + 1)
                         .execution_options(synchronize_session=False))
        db.refresh(ticket)
        if res.rowcount == 0:                       # somebody else admitted it a moment ago
            return self._already_used(msg, db, ticket)

        self._bump(db, "admitted")
        self.send("BookingAgent", P.INFORM,
                  {"action": "ticket_admitted", "booking_id": ticket.booking_id, "ticket_id": ticket.id},
                  db, msg.conversation_id)

        booking = db.get(Booking, ticket.booking_id)
        holder = db.get(User, booking.user_id) if booking else None
        category = db.get(TicketCategory, booking.category_id) if booking else None
        return msg.reply(P.AGREE, {
            "decision": "admit", "reason": "Valid ticket - admitted",
            "holder": holder.name if holder else "?", "category": category.name if category else "?",
            "event_title": event.title})
