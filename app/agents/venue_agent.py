"""VenueAgent - goal: keep every venue's calendar free of clashes.

DECISION RULES (copy these into the report)
Event slots (action: check_slot)
  E1  End time must be after start time, else REFUSE.
  E2  The venue must exist, else REFUSE.
  E3  A slot is refused if it overlaps (including a 30-minute turnaround buffer
      before and after) any draft/published event or confirmed private hire at the venue.
Capacity (action: check_capacity)
  C1  Total tickets across all categories may not exceed venue capacity, else REFUSE.
Private hire (action: hire_request)
  H1  Start must be in the future, end after start, duration 1-12 hours, else REFUSE.
  H2  Venue must exist; if it is not open for hire -> PROPOSE other open venues (else REFUSE).
  H3  Guests must be >= 1 and <= capacity; otherwise PROPOSE bigger venues (else REFUSE).
  H4  If the slot clashes (with buffer) -> PROPOSE other times at the same venue and
      other free venues (else REFUSE).
  H5  Price = hours x hourly rate, +25% if the hire starts on a Saturday or Sunday.
  H6  Escalate to admin (INFORM, status 'escalated') if guests > 100, duration > 6 hours
      or the hire ends after 22:00. Otherwise confirm automatically (AGREE).
Admin decision (action: resolve_hire)
  A1  Only escalated requests can be resolved.
  A2  Approval is re-checked for clashes (the slot may have been taken meanwhile).

STATE (persistent counters): slots_accepted, slots_refused, hires_confirmed,
  hires_escalated, hires_countered, hires_refused, hires_approved, hires_rejected
"""
from datetime import datetime, timedelta

from app.agents.base import BaseAgent
from app.agents.messages import Performative as P
from app.models import Venue, Event, HireRequest
from app.models._util import utcnow

TURNAROUND_BUFFER = timedelta(minutes=30)
MIN_HIRE_HOURS = 1
MAX_HIRE_HOURS = 12
WEEKEND_MULTIPLIER = 1.25
ESCALATE_GUESTS = 100
ESCALATE_HOURS = 6
ESCALATE_END_HOUR = 22


def _dt(value) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _fmt(d: datetime) -> str:
    return d.strftime("%d %b %Y %H:%M")


class VenueAgent(BaseAgent):
    name = "VenueAgent"

    # ------------------------------------------------------------ helpers
    def _bump(self, db, key):
        self.set_state(db, key, self.get_state(db, key, 0) + 1)

    def _conflicts(self, db, venue_id, start, end, exclude_event_id=None):
        lo, hi = start - TURNAROUND_BUFFER, end + TURNAROUND_BUFFER
        found = []
        q = db.query(Event).filter(
            Event.venue_id == venue_id, Event.status.in_(["draft", "published"]),
            Event.start_time < hi, Event.end_time > lo)
        if exclude_event_id:
            q = q.filter(Event.id != exclude_event_id)
        for e in q.all():
            found.append({"kind": "event", "id": e.id, "title": e.title,
                          "start_time": e.start_time.isoformat(), "end_time": e.end_time.isoformat()})
        for h in db.query(HireRequest).filter(
                HireRequest.venue_id == venue_id, HireRequest.status == "confirmed",
                HireRequest.start_time < hi, HireRequest.end_time > lo).all():
            found.append({"kind": "hire", "id": h.id, "title": "Private hire",
                          "start_time": h.start_time.isoformat(), "end_time": h.end_time.isoformat()})
        return found

    @staticmethod
    def _describe(conflicts):
        return "; ".join(f"{c['title']} ({_fmt(_dt(c['start_time']))} - {_fmt(_dt(c['end_time']))})"
                         for c in conflicts)

    @staticmethod
    def _price(venue, start, end):
        hours = (end - start).total_seconds() / 3600
        multiplier = WEEKEND_MULTIPLIER if start.weekday() >= 5 else 1.0
        return round(hours * float(venue.hourly_rate) * multiplier, 2)

    def _alt(self, kind, venue, start, end):
        return {"type": kind, "venue_id": venue.id, "venue_name": venue.name,
                "start_time": start.isoformat(), "end_time": end.isoformat(),
                "price": self._price(venue, start, end)}

    def _alt_venues(self, db, venue, start, end, guests):
        out = []
        q = db.query(Venue).filter(Venue.open_for_hire == True, Venue.capacity >= guests)  # noqa: E712
        for v in q.all():
            if venue is not None and v.id == venue.id:
                continue
            if not self._conflicts(db, v.id, start, end):
                out.append(self._alt("other_venue", v, start, end))
            if len(out) == 3:
                break
        return out

    def _alt_times(self, db, venue, start, end):
        duration, out = end - start, []
        candidates = []
        for k in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6):          # same day first
            candidates.append(start + timedelta(hours=k))
        for d in range(1, 8):                                          # then following days
            candidates.append(start + timedelta(days=d))
        now = utcnow()
        for s in candidates:
            e = s + duration
            if s <= now or e.date() != s.date():
                continue
            if not self._conflicts(db, venue.id, s, e):
                out.append(self._alt("other_time", venue, s, e))
            if len(out) == 3:
                break
        return out

    def _refuse(self, msg, db, counter, reason, **extra):
        self._bump(db, counter)
        return msg.reply(P.REFUSE, {"reason": reason, **extra})

    # ------------------------------------------------------------ event slots
    def on_check_slot(self, msg, db):
        c = msg.content
        try:
            venue_id, start, end = int(c["venue_id"]), _dt(c["start_time"]), _dt(c["end_time"])
        except (KeyError, ValueError, TypeError):
            return msg.reply(P.FAILURE, {"reason": "venue_id, start_time and end_time are required"})

        if end <= start:                                                           # E1
            return self._refuse(msg, db, "slots_refused", "End time must be after start time")
        if db.get(Venue, venue_id) is None:                                        # E2
            return self._refuse(msg, db, "slots_refused", "Venue does not exist")
        conflicts = self._conflicts(db, venue_id, start, end, c.get("exclude_event_id"))
        if conflicts:                                                              # E3
            return self._refuse(
                msg, db, "slots_refused",
                f"Venue is not free (30-minute turnaround buffer applies): {self._describe(conflicts)}",
                conflicts=conflicts)
        self._bump(db, "slots_accepted")
        return msg.reply(P.AGREE, {"venue_id": venue_id, "buffer_minutes": 30})

    def on_check_capacity(self, msg, db):
        c = msg.content
        venue = db.get(Venue, int(c.get("venue_id", 0)))
        if venue is None:
            return msg.reply(P.FAILURE, {"reason": "Venue does not exist"})
        total = int(c.get("total_tickets", 0))
        if total > venue.capacity:                                                 # C1
            return msg.reply(P.REFUSE, {
                "reason": f"Total tickets ({total}) exceed venue capacity ({venue.capacity})",
                "capacity": venue.capacity})
        return msg.reply(P.AGREE, {"capacity": venue.capacity})

    # ------------------------------------------------------------ private hire
    def on_hire_request(self, msg, db):
        c = msg.content
        try:
            venue_id, user_id = int(c["venue_id"]), int(c["user_id"])
            start, end, guests = _dt(c["start_time"]), _dt(c["end_time"]), int(c["guests"])
        except (KeyError, ValueError, TypeError):
            return msg.reply(P.FAILURE, {"reason": "venue_id, user_id, start_time, end_time, guests required"})

        hours = (end - start).total_seconds() / 3600
        if end <= start or start <= utcnow():                                      # H1
            return self._refuse(msg, db, "hires_refused", "Hire must start in the future and end after it starts")
        if not (MIN_HIRE_HOURS <= hours <= MAX_HIRE_HOURS):
            return self._refuse(msg, db, "hires_refused",
                                f"Hire duration must be between {MIN_HIRE_HOURS} and {MAX_HIRE_HOURS} hours")

        venue = db.get(Venue, venue_id)
        if venue is None:                                                          # H2
            return self._refuse(msg, db, "hires_refused", "Venue does not exist")
        if guests < 1:
            return self._refuse(msg, db, "hires_refused", "Guest count must be at least 1")

        problem = None
        if not venue.open_for_hire:
            problem = f"{venue.name} is not open for private hire"
        elif guests > venue.capacity:                                              # H3
            problem = f"{guests} guests exceed the capacity of {venue.name} ({venue.capacity})"
        else:
            conflicts = self._conflicts(db, venue.id, start, end)
            if conflicts:                                                          # H4
                problem = f"{venue.name} is not free at that time: {self._describe(conflicts)}"

        if problem:
            alts = []
            if venue.open_for_hire and guests <= venue.capacity:
                alts += self._alt_times(db, venue, start, end)
            alts += self._alt_venues(db, venue, start, end, guests)
            if not alts:
                return self._refuse(msg, db, "hires_refused", problem + ". No alternatives are available.")
            self._bump(db, "hires_countered")
            return msg.reply(P.PROPOSE, {"reason": problem, "alternatives": alts})

        price = self._price(venue, start, end)                                     # H5
        weekend = start.weekday() >= 5
        reasons = []                                                               # H6
        if guests > ESCALATE_GUESTS:
            reasons.append(f"more than {ESCALATE_GUESTS} guests")
        if hours > ESCALATE_HOURS:
            reasons.append(f"longer than {ESCALATE_HOURS} hours")
        if end.hour > ESCALATE_END_HOUR or (end.hour == ESCALATE_END_HOUR and end.minute > 0):
            reasons.append(f"ends after {ESCALATE_END_HOUR}:00")

        status = "escalated" if reasons else "confirmed"
        reason = ("Needs admin approval: " + ", ".join(reasons)) if reasons else "Routine request, confirmed automatically"
        req = HireRequest(user_id=user_id, venue_id=venue.id, start_time=start, end_time=end,
                          purpose=c.get("purpose", ""), guests=guests, price=price,
                          status=status, decision_reason=reason)
        db.add(req)
        db.flush()

        info = {"request_id": req.id, "user_id": user_id, "venue_name": venue.name,
                "date": _fmt(start), "price": f"{price:,.2f}"}
        self.broadcast("hire_escalated" if reasons else "hire_confirmed", info, db, msg.conversation_id)
        self._bump(db, "hires_escalated" if reasons else "hires_confirmed")

        body = {"decision": status, "request_id": req.id, "price": price,
                "weekend_surcharge": weekend, "reason": reason}
        return msg.reply(P.INFORM if reasons else P.AGREE, body)

    def on_resolve_hire(self, msg, db):
        c = msg.content
        req = db.get(HireRequest, int(c.get("request_id", 0)))
        if req is None:
            return msg.reply(P.FAILURE, {"reason": "Hire request not found"})
        if req.status != "escalated":                                              # A1
            return msg.reply(P.REFUSE, {"reason": f"Request is already {req.status}"})

        venue = db.get(Venue, req.venue_id)
        info = {"request_id": req.id, "user_id": req.user_id, "venue_name": venue.name,
                "date": _fmt(req.start_time), "price": f"{req.price:,.2f}"}

        if c.get("decision") == "approve":
            conflicts = self._conflicts(db, req.venue_id, req.start_time, req.end_time)
            if conflicts:                                                          # A2
                return msg.reply(P.REFUSE, {
                    "reason": f"Slot has since been taken: {self._describe(conflicts)}"})
            req.status, req.decision_reason = "confirmed", c.get("reason") or "Approved by admin"
            self._bump(db, "hires_approved")
            self.broadcast("hire_approved", info, db, msg.conversation_id)
        else:
            req.status = "rejected"
            req.decision_reason = c.get("reason") or "Rejected by admin"
            self._bump(db, "hires_rejected")
            self.broadcast("hire_rejected", {**info, "reason": req.decision_reason}, db, msg.conversation_id)
        db.flush()
        return msg.reply(P.AGREE, {"request_id": req.id, "status": req.status})
