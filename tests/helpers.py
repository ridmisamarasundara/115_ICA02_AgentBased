from datetime import timedelta
from types import SimpleNamespace

from app.agents.booking_agent import BookingAgent
from app.agents.bus import MessageBus
from app.agents.messages import Message, Performative as P
from app.agents.notification_agent import NotificationAgent
from app.agents.ticket_agent import TicketAgent
from app.agents.waitlist_agent import WaitlistAgent
from app.models import Venue, User, Event, TicketCategory
from app.models._util import utcnow


def build_world(db):
    bus = MessageBus()
    booking, ticket, waitlist = BookingAgent(bus), TicketAgent(bus), WaitlistAgent(bus)
    NotificationAgent(bus)
    venue = Venue(name="Main Hall", location="Campus", capacity=500, hourly_rate=1000, open_for_hire=True)
    ann = User(name="Ann", email="ann@x.com", password_hash="x")
    bob = User(name="Bob", email="bob@x.com", password_hash="x")
    carol = User(name="Carol", email="carol@x.com", password_hash="x")
    db.add_all([venue, ann, bob, carol])
    db.commit()
    return SimpleNamespace(bus=bus, booking=booking, ticket=ticket, waitlist=waitlist, db=db,
                           venue=venue, ann=ann, bob=bob, carol=carol)


def make_event(w, days=10, hours_ahead=None, quantity=10, price=500, status="published", title="Concert"):
    start = utcnow() + (timedelta(hours=hours_ahead) if hours_ahead is not None else timedelta(days=days))
    ev = Event(title=title, category="concert", venue_id=w.venue.id, start_time=start,
               end_time=start + timedelta(hours=3), status=status)
    w.db.add(ev)
    w.db.commit()
    cat = TicketCategory(event_id=ev.id, name="General", price=price, quantity=quantity, sold=0)
    w.db.add(cat)
    w.db.commit()
    return ev, cat


def send(w, receiver, action, **content):
    msg = Message(sender="Tester", receiver=receiver, performative=P.REQUEST,
                  content={"action": action, **content})
    return w.bus.send(msg, w.db)


def book(w, user, cat, qty):
    return send(w, "BookingAgent", "book", user_id=user.id, event_id=cat.event_id,
                category_id=cat.id, quantity=qty)


def scan(w, code, event):
    return send(w, "TicketAgent", "scan", code=code, event_id=event.id)
