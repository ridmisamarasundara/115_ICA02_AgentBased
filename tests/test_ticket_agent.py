import pytest

from app.agents.messages import Performative as P
from tests.helpers import build_world, make_event, book, send, scan


@pytest.fixture
def w(db):
    return build_world(db)


def test_codes_are_unique_and_unguessable(w):
    ev, cat = make_event(w, hours_ahead=1)
    codes = book(w, w.ann, cat, 4).content["ticket_codes"]
    assert len(set(codes)) == 4
    assert all(len(c) >= 30 for c in codes)


def test_ticket_is_admitted_once_only(w):
    ev, cat = make_event(w, hours_ahead=1)
    code = book(w, w.ann, cat, 1).content["ticket_codes"][0]
    first = scan(w, code, ev)
    second = scan(w, code, ev)
    assert first.performative == P.AGREE and first.content["decision"] == "admit"
    assert first.content["holder"] == "Ann"
    assert second.performative == P.REFUSE and second.content["decision"] == "already_used"
    assert second.content["scan_count"] == 2
    assert w.ticket.get_state(w.db, "admitted") == 1


def test_ticket_for_another_event_is_rejected(w):
    ev1, cat1 = make_event(w, hours_ahead=1, title="Concert")
    ev2, _ = make_event(w, hours_ahead=1, title="Workshop")
    code = book(w, w.ann, cat1, 1).content["ticket_codes"][0]
    r = scan(w, code, ev2)
    assert r.performative == P.REFUSE and r.content["decision"] == "wrong_event"
    assert "Concert" in r.content["reason"]


def test_cancelled_ticket_is_rejected(w):
    ev, cat = make_event(w, hours_ahead=1)
    b = book(w, w.ann, cat, 1)
    send(w, "BookingAgent", "cancel", booking_id=b.content["booking_id"], user_id=w.ann.id)
    r = scan(w, b.content["ticket_codes"][0], ev)
    assert r.content["decision"] == "cancelled"


def test_unknown_code_is_rejected(w):
    ev, _ = make_event(w, hours_ahead=1)
    r = scan(w, "not-a-real-code", ev)
    assert r.performative == P.REFUSE and r.content["decision"] == "unknown_ticket"


def test_scan_outside_checkin_time_is_rejected(w):
    ev, cat = make_event(w, days=5)
    code = book(w, w.ann, cat, 1).content["ticket_codes"][0]
    r = scan(w, code, ev)
    assert r.performative == P.REFUSE and r.content["decision"] == "outside_checkin_time"


def test_repeated_scans_are_flagged_as_suspicious(w):
    ev, cat = make_event(w, hours_ahead=1)
    code = book(w, w.ann, cat, 1).content["ticket_codes"][0]
    scan(w, code, ev)
    scan(w, code, ev)
    scan(w, code, ev)
    fourth = scan(w, code, ev)
    assert fourth.content["suspicious"] is True
    assert code in w.ticket.get_state(w.db, "suspicious_codes")


def test_ticket_agent_informs_booking_agent_on_admission(w):
    ev, cat = make_event(w, hours_ahead=1)
    code = book(w, w.ann, cat, 1).content["ticket_codes"][0]
    scan(w, code, ev)
    assert w.booking.get_state(w.db, "checkins_seen") == 1
