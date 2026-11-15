from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Booking, Ticket
from tests.web_helpers import client, csrf, login, make_user, post, seed_event, PW  # noqa: F401

ONE_HOUR = 1 / 24          # event starts in an hour: inside the 2-hour check-in window


def staff_client():
    make_user("staff@x.com", "staff")
    c = TestClient(app)
    c.__enter__()
    login(c, "staff@x.com")
    return c


def api_scan(staff, code, event_id, token=None):
    token = token or csrf(staff, "/staff/scan")
    return staff.post("/api/scan", json={"code": code, "event_id": event_id}, headers={"X-CSRF-Token": token})


def ticket_codes():
    with SessionLocal() as db:
        return [t.code for t in db.query(Ticket).order_by(Ticket.id).all()]


def book(client, ev_id, cat_id, qty=1):
    make_user("ann@x.com")
    login(client, "ann@x.com")
    post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=qty)
    return ticket_codes()


def test_scanner_page_lists_events_and_has_camera_and_manual_entry(client):
    seed_event(days=ONE_HOUR, title="Gate Concert")
    make_user("staff@x.com", "staff")
    login(client, "staff@x.com")
    page = client.get("/staff/scan").text
    assert "Gate Concert" in page and 'id="reader"' in page and 'id="manual-code"' in page


def test_ticket_is_admitted_once_and_second_scan_is_rejected(client):
    ev_id, cat_id, _ = seed_event(days=ONE_HOUR)
    code = book(client, ev_id, cat_id)[0]
    staff = staff_client()
    first = api_scan(staff, code, ev_id).json()
    second = api_scan(staff, code, ev_id).json()
    assert first["ok"] is True and first["decision"] == "admit" and first["holder"]
    assert second["ok"] is False and second["decision"] == "already_used"
    assert "already used" in second["reason"].lower()


def test_wrong_event_unknown_and_cancelled_tickets_are_rejected_with_reasons(client):
    ev1, cat1, _ = seed_event(days=ONE_HOUR, title="Concert A")
    ev2, _, _ = seed_event(days=ONE_HOUR, title="Concert B")
    code = book(client, ev1, cat1)[0]
    staff = staff_client()

    wrong = api_scan(staff, code, ev2).json()
    assert wrong["decision"] == "wrong_event" and "Concert A" in wrong["reason"]
    assert api_scan(staff, "no-such-code", ev1).json()["decision"] == "unknown_ticket"

    with SessionLocal() as db:
        booking_id = db.query(Booking).one().id
    post(client, f"/bookings/{booking_id}/cancel")
    cancelled = api_scan(staff, code, ev1).json()
    assert cancelled["decision"] == "cancelled" and cancelled["ok"] is False


def test_scan_outside_checkin_time_is_rejected(client):
    ev_id, cat_id, _ = seed_event(days=5)
    code = book(client, ev_id, cat_id)[0]
    staff = staff_client()
    r = api_scan(staff, code, ev_id).json()
    assert r["decision"] == "outside_checkin_time" and "opens" in r["reason"]


def test_repeated_scans_are_flagged_suspicious(client):
    ev_id, cat_id, _ = seed_event(days=ONE_HOUR)
    code = book(client, ev_id, cat_id)[0]
    staff = staff_client()
    results = [api_scan(staff, code, ev_id).json() for _ in range(4)]
    assert results[-1]["suspicious"] is True and results[-1]["scan_count"] >= 3


def test_scan_api_requires_csrf_token_and_staff_role(client):
    ev_id, cat_id, _ = seed_event(days=ONE_HOUR)
    code = book(client, ev_id, cat_id)[0]
    staff = staff_client()

    no_token = staff.post("/api/scan", json={"code": code, "event_id": ev_id})
    assert no_token.status_code == 403
    assert api_scan(staff, code, ev_id, token="forged-token").status_code == 403

    # the attendee (logged in on `client`) must not be able to use the scanner API
    attendee = api_scan(client, code, ev_id, token=csrf(client, "/login"))
    assert attendee.status_code == 403

    with TestClient(app) as anonymous:
        assert anonymous.post("/api/scan", json={"code": code, "event_id": ev_id}).status_code in (401, 403)
