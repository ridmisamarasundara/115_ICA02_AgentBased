from datetime import timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Event, HireRequest, TicketCategory, Venue
from app.models._util import utcnow
from tests.web_helpers import client, csrf, login, make_user, post, seed_event, PW  # noqa: F401

FMT = "%Y-%m-%dT%H:%M"


def admin_client(client):
    make_user("admin@x.com", "admin")
    login(client, "admin@x.com")
    return client


def slot(days=15, hour=18, hours=3):
    start = (utcnow() + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return start.strftime(FMT), (start + timedelta(hours=hours)).strftime(FMT)


def event_form(venue_id, title="Admin Concert", qty="10", action="publish", days=15, hour=18, **extra):
    start, end = slot(days, hour)
    data = {"title": title, "category": "concert", "venue_id": venue_id, "start_time": start, "end_time": end,
            "description": "Created by admin", "action": action,
            "cat_id": [""], "cat_name": ["General"], "cat_price": ["500"], "cat_qty": [qty]}
    data.update(extra)
    return data


def new_venue(client, capacity=100, name="Test Hall"):
    r = post(client, "/admin/venues/new", name=name, location="Campus", capacity=capacity, description="",
             image_url="", hourly_rate="1000", open_for_hire="on")
    assert r.status_code == 303
    with SessionLocal() as db:
        return db.query(Venue).filter_by(name=name).one().id


def test_admin_pages_are_forbidden_for_staff_and_attendees(client):
    make_user("staff@x.com", "staff")
    login(client, "staff@x.com")
    for path in ("/admin/venues", "/admin/events", "/admin/hire", "/admin/messages", "/admin/agents"):
        assert client.get(path).status_code == 403


def test_admin_can_create_and_validate_venues(client):
    admin_client(client)
    venue_id = new_venue(client)
    assert "Test Hall" in client.get("/admin/venues").text
    bad = post(client, "/admin/venues/new", name="X Hall", location="Campus", capacity="0", description="",
               image_url="javascript:alert(1)", hourly_rate="10")
    assert bad.status_code == 400
    assert "Capacity" in bad.text and "http" in bad.text
    edit = post(client, f"/admin/venues/{venue_id}/edit", name="Test Hall", location="Campus", capacity="250",
                description="", image_url="", hourly_rate="1200")
    assert edit.status_code == 303
    with SessionLocal() as db:
        v = db.get(Venue, venue_id)
        assert v.capacity == 250 and v.open_for_hire is False


def test_event_draft_then_publish(client):
    admin_client(client)
    venue_id = new_venue(client)
    r = post(client, "/admin/events/new", **event_form(venue_id, action="draft"))
    assert r.status_code == 303
    assert "Admin Concert" not in client.get("/").text                  # drafts are not public
    with SessionLocal() as db:
        ev = db.query(Event).filter_by(title="Admin Concert").one()
        assert ev.status == "draft" and len(ev.categories) == 1
        ev_id = ev.id
    assert post(client, f"/admin/events/{ev_id}/publish").status_code == 303
    assert "Admin Concert" in client.get("/").text


def test_tickets_cannot_exceed_venue_capacity(client):
    admin_client(client)
    venue_id = new_venue(client, capacity=100)
    r = post(client, "/admin/events/new", **event_form(venue_id, qty="101"))
    assert r.status_code == 400 and "exceed venue capacity" in r.text


def test_overlapping_events_at_a_venue_are_refused(client):
    admin_client(client)
    venue_id = new_venue(client)
    assert post(client, "/admin/events/new", **event_form(venue_id, title="First")).status_code == 303
    clash = post(client, "/admin/events/new", **event_form(venue_id, title="Second", hour=19))
    assert clash.status_code == 400 and "not free" in clash.text
    after_buffer = post(client, "/admin/events/new", **event_form(venue_id, title="Third", hour=21))   # 21:00 + 30 min buffer
    assert after_buffer.status_code == 303


def test_event_needs_a_ticket_category(client):
    admin_client(client)
    venue_id = new_venue(client)
    r = post(client, "/admin/events/new", **event_form(venue_id, cat_id=[""], cat_name=[""], cat_price=[""], cat_qty=[""]))
    assert r.status_code == 400 and "at least one ticket category" in r.text


def test_cancelling_a_published_event_refunds_all_bookings(client):
    ev_id, cat_id, _ = seed_event(days=1, price=500)           # only 1 day away: a normal cancel would refund 0%
    make_user("ann@x.com")
    login(client, "ann@x.com")
    post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=2)
    with TestClient(app) as admin:
        make_user("admin@x.com", "admin")
        login(admin, "admin@x.com")
        assert post(admin, f"/admin/events/{ev_id}/cancel").status_code == 303
        assert "cancelled" in admin.get("/admin/events").text
    bookings = client.get("/bookings").text
    assert "Cancelled" in bookings and "1,000.00" in bookings          # full refund even this close to the event
    assert "was cancelled" in client.get("/notifications").text


def test_edit_is_limited_once_tickets_are_sold(client):
    ev_id, cat_id, _ = seed_event(days=10)
    make_user("ann@x.com")
    login(client, "ann@x.com")
    post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=1)
    with SessionLocal() as db:
        original_start = db.get(Event, ev_id).start_time
    with TestClient(app) as admin:
        make_user("admin@x.com", "admin")
        login(admin, "admin@x.com")
        r = post(admin, f"/admin/events/{ev_id}/edit", title="Renamed Concert", category="concert", venue_id="1",
                 start_time=slot(30)[0], end_time=slot(30)[1], description="New text")
        assert r.status_code == 303
    with SessionLocal() as db:
        ev = db.get(Event, ev_id)
        assert ev.title == "Renamed Concert" and ev.start_time == original_start


def test_admin_approves_an_escalated_hire_request(client):
    _, _, venue_id = seed_event()
    make_user("ann@x.com")
    login(client, "ann@x.com")
    start = (utcnow() + timedelta(days=8)).replace(hour=10, minute=0, second=0, microsecond=0)
    r = post(client, "/hire", venue_id=venue_id, start_time=start.strftime(FMT),
             end_time=(start + timedelta(hours=3)).strftime(FMT), guests=150, purpose="Big reception")
    assert r.status_code == 303
    assert "waiting for admin" in client.get("/hire/my").text
    with SessionLocal() as db:
        req_id = db.query(HireRequest).one().id
    with TestClient(app) as admin:
        make_user("admin@x.com", "admin")
        login(admin, "admin@x.com")
        assert "Big reception" in admin.get("/admin/hire").text
        assert post(admin, f"/admin/hire/{req_id}/resolve", decision="approve", reason="").status_code == 303
    assert "confirmed" in client.get("/hire/my").text
    assert "approved" in client.get("/notifications").text


def test_dashboard_shows_sales_revenue_and_checkins(client):
    ev_id, cat_id, _ = seed_event(title="Dashboard Concert", price=500)
    make_user("ann@x.com")
    login(client, "ann@x.com")
    post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=2)
    with TestClient(app) as admin:
        make_user("admin@x.com", "admin")
        login(admin, "admin@x.com")
        page = admin.get("/admin").text
        assert "Dashboard Concert" in page and "Rs. 1,000.00" in page and "salesChart" in page


def test_message_log_traces_one_action_across_agents(client):
    ev_id, cat_id, _ = seed_event()
    make_user("ann@x.com")
    login(client, "ann@x.com")
    post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=1)
    with TestClient(app) as admin:
        make_user("admin@x.com", "admin")
        login(admin, "admin@x.com")
        page = admin.get("/admin/messages").text
        assert "BookingAgent" in page and "TicketAgent" in page and "NotificationAgent" in page
        conv_id = page.split("conversation=")[1].split('"')[0]
        thread = admin.get(f"/admin/messages?conversation={conv_id}").text
        assert "BookingAgent" in thread and "TicketAgent" in thread
        assert "TicketAgent" in admin.get("/admin/messages?agent=TicketAgent").text
        assert "WaitlistAgent" in admin.get("/admin/agents").text
