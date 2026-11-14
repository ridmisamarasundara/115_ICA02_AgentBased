from datetime import timedelta

import pytest

from app.agents.messages import Performative as P
from app.models import WaitlistEntry, TicketCategory, Notification, Booking
from app.models._util import utcnow
from tests.helpers import build_world, make_event, book, send


@pytest.fixture
def w(db):
    return build_world(db)


def sold_out(w, qty=1):
    ev, cat = make_event(w, quantity=qty)
    b = book(w, w.ann, cat, qty)
    return ev, cat, b


def join(w, user, cat, qty=1):
    return send(w, "WaitlistAgent", "join", user_id=user.id, event_id=cat.event_id,
                category_id=cat.id, quantity=qty)


def cancel(w, b, user):
    return send(w, "BookingAgent", "cancel", booking_id=b.content["booking_id"], user_id=user.id)


def entry(w, entry_id):
    w.db.expire_all()
    return w.db.get(WaitlistEntry, entry_id)


def sold(w, cat):
    w.db.expire_all()
    return w.db.get(TicketCategory, cat.id).sold


def expire_hold(w, entry_id):
    e = entry(w, entry_id)
    e.hold_expires_at = utcnow() - timedelta(minutes=1)
    w.db.commit()


def test_join_refused_while_seats_are_available(w):
    ev, cat = make_event(w, quantity=10)
    r = join(w, w.bob, cat)
    assert r.performative == P.REFUSE and "book directly" in r.content["reason"]


def test_join_when_sold_out_gives_queue_position(w):
    ev, cat, _ = sold_out(w)
    first = join(w, w.bob, cat)
    second = join(w, w.carol, cat)
    assert first.performative == P.AGREE and first.content["position"] == 1
    assert second.content["position"] == 2


def test_cannot_join_twice(w):
    ev, cat, _ = sold_out(w)
    join(w, w.bob, cat)
    assert join(w, w.bob, cat).performative == P.REFUSE


def test_freed_seat_is_held_for_first_in_line_only(w):
    ev, cat, b = sold_out(w)
    e1 = join(w, w.bob, cat).content["entry_id"]
    e2 = join(w, w.carol, cat).content["entry_id"]
    cancel(w, b, w.ann)
    assert entry(w, e1).status == "held"
    assert entry(w, e1).hold_expires_at > utcnow()
    assert entry(w, e2).status == "waiting"
    assert sold(w, cat) == 1                                       # the seat is held, not free
    assert w.db.query(Notification).filter(Notification.user_id == w.bob.id,
                                           Notification.message.like("%held%")).count() == 1


def test_held_seat_cannot_be_bought_by_someone_else(w):
    ev, cat, b = sold_out(w)
    join(w, w.bob, cat)
    cancel(w, b, w.ann)
    assert book(w, w.carol, cat, 1).performative == P.REFUSE


def test_claim_turns_hold_into_booking_without_double_counting_seats(w):
    ev, cat, b = sold_out(w)
    e = join(w, w.bob, cat).content["entry_id"]
    cancel(w, b, w.ann)
    r = send(w, "WaitlistAgent", "claim", entry_id=e, user_id=w.bob.id)
    assert r.performative == P.AGREE and len(r.content["ticket_codes"]) == 1
    assert entry(w, e).status == "claimed"
    assert sold(w, cat) == 1
    assert w.db.query(Booking).filter_by(user_id=w.bob.id, status="confirmed").count() == 1


def test_only_the_owner_can_claim(w):
    ev, cat, b = sold_out(w)
    e = join(w, w.bob, cat).content["entry_id"]
    cancel(w, b, w.ann)
    assert send(w, "WaitlistAgent", "claim", entry_id=e, user_id=w.carol.id).performative == P.REFUSE


def test_claim_after_expiry_is_refused_and_next_person_is_offered(w):
    ev, cat, b = sold_out(w)
    e1 = join(w, w.bob, cat).content["entry_id"]
    e2 = join(w, w.carol, cat).content["entry_id"]
    cancel(w, b, w.ann)
    expire_hold(w, e1)
    r = send(w, "WaitlistAgent", "claim", entry_id=e1, user_id=w.bob.id)
    assert r.performative == P.REFUSE and "expired" in r.content["reason"]
    assert entry(w, e1).status == "expired"
    assert entry(w, e2).status == "held"


def test_timer_sweep_expires_holds_and_reoffers_automatically(w):
    ev, cat, b = sold_out(w)
    e1 = join(w, w.bob, cat).content["entry_id"]
    e2 = join(w, w.carol, cat).content["entry_id"]
    cancel(w, b, w.ann)
    expire_hold(w, e1)

    expired = w.waitlist.tick(w.db)                                # what the 30-second timer does

    assert expired == 1
    assert entry(w, e1).status == "expired"
    assert entry(w, e2).status == "held"
    assert sold(w, cat) == 1
    assert w.waitlist.get_state(w.db, "expired_holds") == 1
    assert w.db.query(Notification).filter(Notification.user_id == w.bob.id,
                                           Notification.message.like("%expired%")).count() == 1


def test_sweep_with_nothing_to_expire_still_records_last_sweep(w):
    assert w.waitlist.tick(w.db) == 0
    assert w.waitlist.get_state(w.db, "last_sweep") is not None


def test_leaving_while_holding_passes_seat_on(w):
    ev, cat, b = sold_out(w)
    e1 = join(w, w.bob, cat).content["entry_id"]
    e2 = join(w, w.carol, cat).content["entry_id"]
    cancel(w, b, w.ann)
    assert send(w, "WaitlistAgent", "leave", entry_id=e1, user_id=w.bob.id).performative == P.AGREE
    assert entry(w, e1).status == "cancelled"
    assert entry(w, e2).status == "held"


def test_event_cancellation_clears_waitlist(w):
    ev, cat, _ = sold_out(w)
    e = join(w, w.bob, cat).content["entry_id"]
    send(w, "BookingAgent", "cancel_event", event_id=ev.id)
    assert entry(w, e).status == "cancelled"
    assert w.db.query(Notification).filter(Notification.user_id == w.bob.id,
                                           Notification.message.like("%waitlist%")).count() == 1
