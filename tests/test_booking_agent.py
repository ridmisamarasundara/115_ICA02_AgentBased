import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.agents.messages import Performative as P
from app.models import Booking, Ticket, TicketCategory, MessageLog, Notification, Event
from tests.helpers import build_world, make_event, book, send, scan


@pytest.fixture
def w(db):
    return build_world(db)


def sold(w, cat):
    w.db.expire_all()
    return w.db.get(TicketCategory, cat.id).sold


def test_successful_booking_with_payment_reference_and_tickets(w):
    ev, cat = make_event(w)
    r = book(w, w.ann, cat, 3)
    assert r.performative == P.AGREE
    assert r.content["payment_reference"].startswith("PAY-")
    assert r.content["total"] == 1500.0
    assert len(r.content["ticket_codes"]) == 3
    assert w.db.query(Ticket).count() == 3
    assert sold(w, cat) == 3
    assert w.booking.get_state(w.db, "tickets_sold") == 3


def test_more_than_six_tickets_refused_with_reason(w):
    ev, cat = make_event(w)
    r = book(w, w.ann, cat, 7)
    assert r.performative == P.REFUSE
    assert "6" in r.content["reason"]
    assert sold(w, cat) == 0


def test_last_seat_can_only_be_sold_once(w):
    ev, cat = make_event(w, quantity=1)
    first = book(w, w.ann, cat, 1)
    second = book(w, w.bob, cat, 1)
    assert first.performative == P.AGREE
    assert second.performative == P.REFUSE
    assert second.content["can_join_waitlist"] is True
    assert sold(w, cat) == 1


def test_never_oversells_across_several_bookings(w):
    ev, cat = make_event(w, quantity=10)
    assert book(w, w.ann, cat, 6).performative == P.AGREE
    assert book(w, w.bob, cat, 4).performative == P.AGREE
    refused = book(w, w.ann, cat, 1)
    assert refused.performative == P.REFUSE
    assert sold(w, cat) == 10
    assert w.db.query(Ticket).count() == 10


def test_atomic_update_ignores_stale_in_memory_state(w):
    """Another request sold the seats after we loaded the category: we must still refuse."""
    ev, cat = make_event(w, quantity=5)
    assert cat.sold == 0                                         # stale copy in this session
    w.db.execute(text("UPDATE ticket_categories SET sold = quantity WHERE id = :i"), {"i": cat.id})
    r = book(w, w.ann, cat, 1)
    assert r.performative == P.REFUSE
    assert sold(w, cat) == 5


def test_database_constraint_blocks_overselling_even_if_agent_is_bypassed(w):
    ev, cat = make_event(w, quantity=5)
    with pytest.raises(IntegrityError):
        w.db.execute(text("UPDATE ticket_categories SET sold = quantity + 1 WHERE id = :i"), {"i": cat.id})
    w.db.rollback()


def test_unpublished_or_started_events_are_not_on_sale(w):
    _, draft_cat = make_event(w, status="draft")
    assert book(w, w.ann, draft_cat, 1).performative == P.REFUSE
    _, started_cat = make_event(w, hours_ahead=-1)
    assert book(w, w.ann, started_cat, 1).performative == P.REFUSE


def test_per_user_limit_per_event(w):
    ev, cat = make_event(w, quantity=50)
    assert book(w, w.ann, cat, 6).performative == P.AGREE
    assert book(w, w.ann, cat, 4).performative == P.AGREE
    r = book(w, w.ann, cat, 1)
    assert r.performative == P.REFUSE and "10" in r.content["reason"]


@pytest.mark.parametrize("days,percent", [(10, 100), (3, 50), (1, 0)])
def test_refund_policy(w, days, percent):
    ev, cat = make_event(w, days=days, price=500)
    b = book(w, w.ann, cat, 2)
    r = send(w, "BookingAgent", "cancel", booking_id=b.content["booking_id"], user_id=w.ann.id)
    assert r.performative == P.AGREE
    assert r.content["refund_percent"] == percent
    assert r.content["refund"] == 1000.0 * percent / 100


def test_cancel_releases_seats_cancels_tickets_and_informs_waitlist_agent(w):
    ev, cat = make_event(w)
    b = book(w, w.ann, cat, 4)
    send(w, "BookingAgent", "cancel", booking_id=b.content["booking_id"], user_id=w.ann.id)
    w.db.expire_all()
    assert sold(w, cat) == 0
    assert w.db.get(Booking, b.content["booking_id"]).status == "cancelled"
    assert {t.status for t in w.db.query(Ticket).all()} == {"cancelled"}
    logged = w.db.query(MessageLog).filter_by(receiver="WaitlistAgent").all()
    assert len(logged) == 1 and logged[0].content["action"] == "seats_freed"


def test_cannot_cancel_someone_elses_booking(w):
    ev, cat = make_event(w)
    b = book(w, w.ann, cat, 1)
    r = send(w, "BookingAgent", "cancel", booking_id=b.content["booking_id"], user_id=w.bob.id)
    assert r.performative == P.REFUSE


def test_cannot_cancel_after_check_in(w):
    ev, cat = make_event(w, hours_ahead=1)
    b = book(w, w.ann, cat, 2)
    assert scan(w, b.content["ticket_codes"][0], ev).performative == P.AGREE
    r = send(w, "BookingAgent", "cancel", booking_id=b.content["booking_id"], user_id=w.ann.id)
    assert r.performative == P.REFUSE and "already used" in r.content["reason"]
    assert sold(w, cat) == 2


def test_event_cancellation_fully_refunds_everyone(w):
    ev, cat = make_event(w, days=1, price=500)
    a = book(w, w.ann, cat, 2)
    book(w, w.bob, cat, 1)
    r = send(w, "BookingAgent", "cancel_event", event_id=ev.id)
    assert r.performative == P.AGREE
    assert r.content["bookings_refunded"] == 2 and r.content["total_refunded"] == 1500.0
    w.db.expire_all()
    assert w.db.get(Event, ev.id).status == "cancelled"
    assert w.db.get(Booking, a.content["booking_id"]).refund_amount == 1000.0
    assert {t.status for t in w.db.query(Ticket).all()} == {"cancelled"}
    assert w.db.query(Notification).filter(Notification.message.like("%cancelled%")).count() == 2
    again = send(w, "BookingAgent", "cancel_event", event_id=ev.id)
    assert again.performative == P.REFUSE
