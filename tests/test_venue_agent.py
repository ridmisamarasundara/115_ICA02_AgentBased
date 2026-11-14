from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.agents.bus import MessageBus
from app.agents.messages import Message, Performative as P
from app.agents.notification_agent import NotificationAgent
from app.agents.venue_agent import VenueAgent
from app.models import Venue, User, Event, HireRequest, Notification
from app.models._util import utcnow


def future(weekday, hour=10):
    d = utcnow() + timedelta(days=8)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


@pytest.fixture
def w(db):
    bus = MessageBus()
    agent = VenueAgent(bus)
    NotificationAgent(bus)
    hall = Venue(name="Main Hall", location="Campus", capacity=300, hourly_rate=1000, open_for_hire=True)
    studio = Venue(name="Studio", location="Campus", capacity=50, hourly_rate=500, open_for_hire=True)
    closed = Venue(name="Lab", location="Campus", capacity=40, hourly_rate=300, open_for_hire=False)
    user = User(name="Ann", email="ann@x.com", password_hash="x", role="attendee")
    user2 = User(name="Bob", email="bob@x.com", password_hash="x", role="attendee")
    admin = User(name="Root", email="root@x.com", password_hash="x", role="admin")
    db.add_all([hall, studio, closed, user, user2, admin])
    db.commit()
    return SimpleNamespace(bus=bus, agent=agent, hall=hall, studio=studio, closed=closed,
                           user=user, user2=user2, admin=admin, db=db)


def ask(w, action, **content):
    msg = Message(sender="Tester", receiver="VenueAgent", performative=P.REQUEST,
                  content={"action": action, **content})
    return w.bus.send(msg, w.db)


def hire(w, venue, start, hours, guests, user=None):
    return ask(w, "hire_request", venue_id=venue.id, user_id=(user or w.user).id,
               start_time=start.isoformat(), end_time=(start + timedelta(hours=hours)).isoformat(),
               guests=guests, purpose="Farewell")


def add_event(w, start, end, status="published"):
    w.db.add(Event(title="Concert", category="concert", venue_id=w.hall.id,
                   start_time=start, end_time=end, status=status))
    w.db.commit()


# ---- event slots -----------------------------------------------------
def test_slot_free_is_agreed(w):
    s = future(0, 15)
    r = ask(w, "check_slot", venue_id=w.hall.id, start_time=s.isoformat(),
            end_time=(s + timedelta(hours=2)).isoformat())
    assert r.performative == P.AGREE


def test_overlapping_slot_is_refused_with_reason(w):
    s = future(0, 15)
    add_event(w, s, s + timedelta(hours=3))
    r = ask(w, "check_slot", venue_id=w.hall.id, start_time=(s + timedelta(hours=1)).isoformat(),
            end_time=(s + timedelta(hours=4)).isoformat())
    assert r.performative == P.REFUSE
    assert "Concert" in r.content["reason"]


def test_turnaround_buffer_is_enforced(w):
    s = future(0, 15)
    add_event(w, s, s + timedelta(hours=3))                       # ends 18:00
    end_ev = s + timedelta(hours=3)
    too_soon = ask(w, "check_slot", venue_id=w.hall.id, start_time=(end_ev + timedelta(minutes=15)).isoformat(),
                   end_time=(end_ev + timedelta(hours=2)).isoformat())
    ok = ask(w, "check_slot", venue_id=w.hall.id, start_time=(end_ev + timedelta(minutes=30)).isoformat(),
             end_time=(end_ev + timedelta(hours=2)).isoformat())
    assert too_soon.performative == P.REFUSE
    assert ok.performative == P.AGREE


def test_capacity_rule(w):
    assert ask(w, "check_capacity", venue_id=w.studio.id, total_tickets=50).performative == P.AGREE
    assert ask(w, "check_capacity", venue_id=w.studio.id, total_tickets=51).performative == P.REFUSE


def test_state_counters_are_persisted(w):
    s = future(0, 15)
    add_event(w, s, s + timedelta(hours=2))
    ask(w, "check_slot", venue_id=w.hall.id, start_time=s.isoformat(), end_time=(s + timedelta(hours=1)).isoformat())
    t = future(1, 9)
    ask(w, "check_slot", venue_id=w.hall.id, start_time=t.isoformat(), end_time=(t + timedelta(hours=1)).isoformat())
    assert w.agent.get_state(w.db, "slots_refused") == 1
    assert w.agent.get_state(w.db, "slots_accepted") == 1


# ---- private hire ----------------------------------------------------
def test_routine_hire_confirmed_with_price(w):
    r = hire(w, w.hall, future(0, 10), 3, 40)                      # Monday
    assert r.performative == P.AGREE
    assert r.content["decision"] == "confirmed"
    assert r.content["price"] == 3000.0
    assert db_status(w) == "confirmed"


def test_weekend_price_surcharge(w):
    r = hire(w, w.hall, future(5, 10), 3, 40)                      # Saturday
    assert r.content["price"] == 3750.0
    assert r.content["weekend_surcharge"] is True


def test_clash_gets_proposal_with_alternatives(w):
    s = future(0, 10)
    hire(w, w.hall, s, 3, 40)
    r = hire(w, w.hall, s, 3, 40, user=w.user2)
    assert r.performative == P.PROPOSE
    assert r.content["alternatives"]
    assert {"other_time", "other_venue"} & {a["type"] for a in r.content["alternatives"]}


def test_not_open_for_hire_proposes_other_venues(w):
    r = hire(w, w.closed, future(1, 10), 2, 10)
    assert r.performative == P.PROPOSE
    assert all(a["venue_id"] != w.closed.id for a in r.content["alternatives"])


def test_too_many_guests_proposes_bigger_venue(w):
    r = hire(w, w.studio, future(1, 10), 2, 80)
    assert r.performative == P.PROPOSE
    assert r.content["alternatives"][0]["venue_name"] == "Main Hall"


def test_hire_in_the_past_is_refused(w):
    r = hire(w, w.hall, utcnow() - timedelta(days=1), 2, 10)
    assert r.performative == P.REFUSE


def test_large_hire_escalates_then_admin_approves_and_users_are_notified(w):
    r = hire(w, w.hall, future(2, 10), 3, 150)
    assert r.performative == P.INFORM and r.content["decision"] == "escalated"
    assert w.db.query(Notification).filter_by(user_id=w.admin.id).count() == 1   # admin told

    done = ask(w, "resolve_hire", request_id=r.content["request_id"], decision="approve")
    assert done.performative == P.AGREE
    assert db_status(w) == "confirmed"
    assert w.db.query(Notification).filter_by(user_id=w.user.id).count() == 2    # escalated + approved


def test_approval_refused_if_slot_taken_meanwhile(w):
    s = future(2, 10)
    r = hire(w, w.hall, s, 3, 150)                                 # escalated, not yet blocking
    hire(w, w.hall, s, 3, 20, user=w.user2)                        # small hire confirmed same slot
    done = ask(w, "resolve_hire", request_id=r.content["request_id"], decision="approve")
    assert done.performative == P.REFUSE


def db_status(w):
    w.db.expire_all()
    return w.db.query(HireRequest).order_by(HireRequest.id).first().status
