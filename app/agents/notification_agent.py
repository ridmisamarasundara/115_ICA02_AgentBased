"""NotificationAgent - goal: tell the right person what affects them.

REACTIVE agent: it only listens to broadcast INFORM events and turns them into
Notification rows. It never decides business outcomes.

RULES
  N1  An event with a known template and a user_id creates one notification for that user.
  N2  Some events (hire_escalated) also notify every admin.
  N3  Unknown events are ignored.
STATE: notifications_created (counter)
"""
from app.agents.base import BaseAgent
from app.models import Notification, User

USER_TEMPLATES = {
    "hire_confirmed": "Your hire of {venue_name} on {date} is confirmed. Price: {price}.",
    "hire_escalated": "Your hire request for {venue_name} on {date} is waiting for admin approval.",
    "hire_approved": "Good news! Your hire of {venue_name} on {date} was approved. Price: {price}.",
    "hire_rejected": "Your hire request for {venue_name} on {date} was rejected. Reason: {reason}",
    # used by later agents
    "booking_confirmed": "Booking #{booking_id} confirmed: {quantity} ticket(s) for {event_title}.",
    "booking_cancelled": "Booking #{booking_id} cancelled. Refund: {refund}.",
    "event_cancelled": "{event_title} was cancelled. You have been fully refunded ({refund}).",
    "seats_held": "Seats for {event_title} are being held for you until {expires}.",
    "hold_expired": "Your held seats for {event_title} expired and were offered to someone else.",
    "waitlist_removed": "{event_title} was cancelled, so you were removed from its waitlist.",
}
ADMIN_TEMPLATES = {
    "hire_escalated": "Hire request #{request_id} for {venue_name} on {date} needs your approval.",
}


class _Safe(dict):
    def __missing__(self, key):
        return "?"


class NotificationAgent(BaseAgent):
    name = "NotificationAgent"
    listens_to_broadcast = True

    def _notify(self, db, user_id, text):
        db.add(Notification(user_id=user_id, message=text))
        self.set_state(db, "notifications_created", self.get_state(db, "notifications_created", 0) + 1)

    def handle(self, msg, db):
        event = msg.content.get("event")
        data = _Safe(msg.content)
        template, user_id = USER_TEMPLATES.get(event), msg.content.get("user_id")
        if template and user_id:                                                   # N1
            self._notify(db, user_id, template.format_map(data))
        admin_template = ADMIN_TEMPLATES.get(event)
        if admin_template:                                                         # N2
            for admin in db.query(User).filter_by(role="admin").all():
                self._notify(db, admin.id, admin_template.format_map(data))
        db.flush()
        return None                                                                # N3 (ignore the rest)
