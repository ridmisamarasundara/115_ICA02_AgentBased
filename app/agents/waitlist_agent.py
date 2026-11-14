"""WaitlistAgent - goal: pass freed seats to waiting customers.

DECISION RULES (copy into the report)
Joining (action: join)
  W1  Only for published events that have not started, 1 to 6 tickets, category must belong to the event.
  W2  Refused if enough seats are still available ("book directly").
  W3  One active entry (waiting or held) per user per ticket category.
Offering seats (reactive: INFORM seats_freed from BookingAgent, and from the timer)
  W4  First come, first served. An entry whose quantity does not fit the freed seats is skipped
      (it stays in the queue) so later entries that fit are not blocked.
  W5  Offered seats are RESERVED for 15 minutes using the same atomic UPDATE as BookingAgent,
      so nobody else can buy them. The user is told (seats_held) with the expiry time.
Claiming (action: claim)
  W6  Only the owner can claim, only a held entry, only before the hold expires.
      The booking is made by BookingAgent (from_hold), the entry becomes 'claimed'.
      If booking fails, the seats are released and offered to the next person.
Leaving (action: leave)
  W7  The owner can leave; a held entry releases its seats to the next person.
Proactive timer (tick, runs every 30 seconds with no user action)
  W8  Every held entry past its expiry becomes 'expired', its seats are released, the user is told
      (hold_expired) and the seats are re-offered to the next waiting entry.
Event cancelled (INFORM event_cancelled from BookingAgent)
  W9  All waiting/held entries for the event are cancelled and users are told.
STATE: joined, offers_made, claims, expired_holds, left, last_sweep (time of the last timer run)
"""
from datetime import timedelta

from sqlalchemy import update

from app.agents.base import BaseAgent
from app.agents.messages import Performative as P, new_conversation_id
from app.models import Event, TicketCategory, WaitlistEntry
from app.models._util import utcnow

HOLD_DURATION = timedelta(minutes=15)
MAX_QUANTITY = 6


def _fmt(d):
    return d.strftime("%d %b %Y %H:%M")


class WaitlistAgent(BaseAgent):
    name = "WaitlistAgent"

    # ------------------------------------------------------------ helpers
    def _bump(self, db, key, n=1):
        self.set_state(db, key, self.get_state(db, key, 0) + n)

    def _reserve(self, db, category_id, qty) -> bool:
        res = db.execute(update(TicketCategory).where(
            TicketCategory.id == category_id, TicketCategory.sold + qty <= TicketCategory.quantity)
            .values(sold=TicketCategory.sold + qty).execution_options(synchronize_session=False))
        return res.rowcount > 0

    def _release(self, db, category_id, qty):
        db.execute(update(TicketCategory)
                   .where(TicketCategory.id == category_id, TicketCategory.sold >= qty)
                   .values(sold=TicketCategory.sold - qty).execution_options(synchronize_session=False))

    def _get_entry(self, msg, db):
        c = msg.content
        try:
            entry_id, user_id = int(c["entry_id"]), int(c["user_id"])
        except (KeyError, ValueError, TypeError):
            return None, msg.reply(P.FAILURE, {"reason": "entry_id and user_id are required"})
        entry = db.get(WaitlistEntry, entry_id)
        if entry is None:
            return None, msg.reply(P.FAILURE, {"reason": "Waitlist entry not found"})
        if entry.user_id != user_id:
            return None, msg.reply(P.REFUSE, {"reason": "This is not your waitlist entry"})
        return entry, None

    def _expire(self, db, entry, cid):
        entry.status = "expired"
        db.flush()
        self._release(db, entry.category_id, entry.quantity)
        event = db.get(Event, entry.event_id)
        self._bump(db, "expired_holds")
        self.broadcast("hold_expired", {"user_id": entry.user_id, "entry_id": entry.id,
                                        "event_title": event.title if event else "your event"}, db, cid)

    def _offer_seats(self, db, event_id, category_id, cid):
        """W4 + W5: reserve seats for waiting entries, first come first served."""
        event = db.get(Event, event_id)
        if event is None or event.status != "published" or event.start_time <= utcnow():
            return 0
        waiting = (db.query(WaitlistEntry)
                   .filter_by(event_id=event_id, category_id=category_id, status="waiting")
                   .order_by(WaitlistEntry.created_at, WaitlistEntry.id).all())
        offered = 0
        for entry in waiting:
            if self._reserve(db, category_id, entry.quantity):
                entry.status = "held"
                entry.hold_expires_at = utcnow() + HOLD_DURATION
                db.flush()
                self._bump(db, "offers_made")
                self.broadcast("seats_held", {"user_id": entry.user_id, "entry_id": entry.id,
                                              "event_title": event.title,
                                              "expires": _fmt(entry.hold_expires_at)}, db, cid)
                offered += 1
        return offered

    # ------------------------------------------------------------ requests
    def on_join(self, msg, db):
        c = msg.content
        try:
            user_id, event_id = int(c["user_id"]), int(c["event_id"])
            category_id, qty = int(c["category_id"]), int(c.get("quantity", 1))
        except (KeyError, ValueError, TypeError):
            return msg.reply(P.FAILURE, {"reason": "user_id, event_id, category_id required"})
        event = db.get(Event, event_id)
        if event is None or event.status != "published" or event.start_time <= utcnow() \
                or not 1 <= qty <= MAX_QUANTITY:                                   # W1
            return msg.reply(P.REFUSE, {"reason": "The waitlist is open for published events that have not "
                                                  f"started, for 1 to {MAX_QUANTITY} tickets"})
        cat = db.get(TicketCategory, category_id)
        if cat is None or cat.event_id != event.id:
            return msg.reply(P.REFUSE, {"reason": "Ticket category does not belong to this event"})
        db.refresh(cat)
        left = cat.quantity - cat.sold
        if left >= qty:                                                            # W2
            return msg.reply(P.REFUSE, {"reason": f"{left} ticket(s) are still available - please book directly"})
        if db.query(WaitlistEntry).filter(WaitlistEntry.user_id == user_id,       # W3
                                          WaitlistEntry.category_id == category_id,
                                          WaitlistEntry.status.in_(["waiting", "held"])).first():
            return msg.reply(P.REFUSE, {"reason": "You are already on the waitlist for this category"})
        entry = WaitlistEntry(user_id=user_id, event_id=event.id, category_id=cat.id, quantity=qty)
        db.add(entry)
        db.flush()
        position = db.query(WaitlistEntry).filter(WaitlistEntry.category_id == cat.id,
                                                  WaitlistEntry.status == "waiting",
                                                  WaitlistEntry.id <= entry.id).count()
        self._bump(db, "joined")
        return msg.reply(P.AGREE, {"entry_id": entry.id, "position": position,
                                   "reason": "Added to the waitlist. You will be told when seats are held for you."})

    def on_claim(self, msg, db):
        entry, err = self._get_entry(msg, db)
        if err:
            return err
        if entry.status != "held":                                                 # W6
            return msg.reply(P.REFUSE, {"reason": f"Nothing to claim: your entry is '{entry.status}'"})
        if entry.hold_expires_at <= utcnow():
            self._expire(db, entry, msg.conversation_id)
            self._offer_seats(db, entry.event_id, entry.category_id, msg.conversation_id)
            return msg.reply(P.REFUSE, {"reason": "Your hold expired and the seats were offered to the next person"})
        r = self.send("BookingAgent", P.REQUEST,
                      {"action": "book", "user_id": entry.user_id, "event_id": entry.event_id,
                       "category_id": entry.category_id, "quantity": entry.quantity, "from_hold": True},
                      db, msg.conversation_id)
        if r is not None and r.performative == P.AGREE:
            entry.status = "claimed"
            db.flush()
            self._bump(db, "claims")
            return msg.reply(P.AGREE, r.content)
        reason = r.content.get("reason", "booking failed") if r is not None else "booking failed"
        entry.status = "cancelled"
        db.flush()
        self._release(db, entry.category_id, entry.quantity)
        self._offer_seats(db, entry.event_id, entry.category_id, msg.conversation_id)
        return msg.reply(P.REFUSE, {"reason": f"Could not complete the booking: {reason}"})

    def on_leave(self, msg, db):
        entry, err = self._get_entry(msg, db)
        if err:
            return err
        if entry.status not in ("waiting", "held"):                                # W7
            return msg.reply(P.REFUSE, {"reason": f"Entry is already '{entry.status}'"})
        was_held = entry.status == "held"
        entry.status = "cancelled"
        db.flush()
        if was_held:
            self._release(db, entry.category_id, entry.quantity)
            self._offer_seats(db, entry.event_id, entry.category_id, msg.conversation_id)
        self._bump(db, "left")
        return msg.reply(P.AGREE, {"status": "cancelled"})

    # ------------------------------------------------------------ messages from BookingAgent
    def on_seats_freed(self, msg, db):
        c = msg.content
        self._offer_seats(db, int(c["event_id"]), int(c["category_id"]), msg.conversation_id)
        return None

    def on_event_cancelled(self, msg, db):                                         # W9
        event = db.get(Event, int(msg.content["event_id"]))
        for entry in db.query(WaitlistEntry).filter(WaitlistEntry.event_id == event.id,
                                                    WaitlistEntry.status.in_(["waiting", "held"])).all():
            entry.status = "cancelled"
            self.broadcast("waitlist_removed", {"user_id": entry.user_id, "event_title": event.title},
                           db, msg.conversation_id)
        db.flush()
        return None

    # ------------------------------------------------------------ PROACTIVE behaviour
    def tick(self, db, now=None) -> int:
        """Timer-driven expiry sweep (W8). Runs without any user action."""
        now = now or utcnow()
        expired = (db.query(WaitlistEntry)
                   .filter(WaitlistEntry.status == "held", WaitlistEntry.hold_expires_at <= now)
                   .order_by(WaitlistEntry.id).all())
        if expired:
            cid = new_conversation_id()       # one conversation id lets the dashboard trace the whole chain
            touched = set()
            for entry in expired:
                self._expire(db, entry, cid)
                touched.add((entry.event_id, entry.category_id))
            for event_id, category_id in sorted(touched):
                self._offer_seats(db, event_id, category_id, cid)
        self.set_state(db, "last_sweep", now.isoformat())
        db.flush()
        return len(expired)
