import re
from datetime import timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import WaitlistEntry
from app.models._util import utcnow
from tests.web_helpers import client, csrf, login, make_user, post, seed_event, PW  # noqa: F401


def test_event_list_only_shows_published_and_supports_search_and_filter(client):
    seed_event(title="Spring Concert", category="concert")
    seed_event(title="Python Workshop", category="workshop")
    seed_event(title="Hidden Draft", status="draft")
    page = client.get("/").text
    assert "Spring Concert" in page and "Python Workshop" in page and "Hidden Draft" not in page
    only_py = client.get("/?q=python").text
    assert "Python Workshop" in only_py and "Spring Concert" not in only_py
    only_concert = client.get("/?category=concert").text
    assert "Spring Concert" in only_concert and "Python Workshop" not in only_concert


def test_draft_event_page_is_not_public(client):
    ev_id, _, _ = seed_event(status="draft")
    assert client.get(f"/events/{ev_id}").status_code == 404


def test_booking_requires_login(client):
    ev_id, cat_id, _ = seed_event()
    r = client.post(f"/events/{ev_id}/book", data={"category_id": cat_id, "quantity": 1,
                                                   "csrf_token": csrf(client)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_booking_flow_shows_reference_qr_and_tickets_left(client):
    ev_id, cat_id, _ = seed_event(quantity=10)
    make_user("ann@x.com")
    login(client, "ann@x.com")
    r = post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=3)
    assert r.status_code == 303 and r.headers["location"].startswith("/bookings/")

    page = client.get(r.headers["location"]).text
    assert "PAY-" in page
    qr_urls = re.findall(r'/tickets/[^"]+/qr\.png', page)
    assert len(qr_urls) == 3
    qr = client.get(qr_urls[0])
    assert qr.status_code == 200 and qr.headers["content-type"] == "image/png"
    assert qr.content[:8] == b"\x89PNG\r\n\x1a\n"

    assert "7 left" in client.get(f"/events/{ev_id}").text


def test_other_users_cannot_see_a_booking_or_its_qr(client):
    ev_id, cat_id, _ = seed_event()
    make_user("ann@x.com")
    make_user("bob@x.com")
    login(client, "ann@x.com")
    r = post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=1)
    booking_url = r.headers["location"]
    qr_url = re.findall(r'/tickets/[^"]+/qr\.png', client.get(booking_url).text)[0]

    with TestClient(app) as bob:
        login(bob, "bob@x.com")
        assert bob.get(booking_url).status_code == 404
        assert bob.get(qr_url).status_code == 404


def test_booking_more_than_six_shows_the_reason(client):
    ev_id, cat_id, _ = seed_event()
    make_user("ann@x.com")
    login(client, "ann@x.com")
    r = post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=7)
    assert r.status_code == 303 and r.headers["location"] == f"/events/{ev_id}"
    assert "1 to 6" in client.get(r.headers["location"]).text


def test_cancel_booking_shows_refund(client):
    ev_id, cat_id, _ = seed_event(days=10, price=500)
    make_user("ann@x.com")
    login(client, "ann@x.com")
    r = post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=2)
    booking_id = r.headers["location"].rsplit("/", 1)[1]
    c = post(client, f"/bookings/{booking_id}/cancel")
    assert c.status_code == 303
    page = client.get("/bookings").text
    assert "Cancelled" in page and "1,000.00" in page


def test_waitlist_flow_through_the_web_pages(client):
    ev_id, cat_id, _ = seed_event(quantity=1)
    make_user("ann@x.com")
    make_user("bob@x.com")
    login(client, "ann@x.com")
    booking_url = post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=1).headers["location"]
    booking_id = booking_url.rsplit("/", 1)[1]

    with TestClient(app) as bob:
        login(bob, "bob@x.com")
        assert "Sold out" in bob.get(f"/events/{ev_id}").text
        assert post(bob, f"/events/{ev_id}/waitlist", category_id=cat_id, quantity=1).status_code == 303
        assert "in line" in bob.get(f"/events/{ev_id}").text

        post(client, f"/bookings/{booking_id}/cancel")                 # Ann cancels -> seat held for Bob
        assert "Seats held for you" in bob.get(f"/events/{ev_id}").text
        with SessionLocal() as db:
            entry_id = db.query(WaitlistEntry).filter_by(status="held").one().id
        claim = post(bob, f"/waitlist/{entry_id}/claim")
        assert claim.status_code == 303 and claim.headers["location"].startswith("/bookings/")


def hire_data(venue_id, days=8, hours=3, guests=20, start_hour=10):
    start = (utcnow() + timedelta(days=days)).replace(hour=start_hour, minute=0, second=0, microsecond=0)
    fmt = "%Y-%m-%dT%H:%M"
    return {"venue_id": venue_id, "start_time": start.strftime(fmt),
            "end_time": (start + timedelta(hours=hours)).strftime(fmt), "guests": guests, "purpose": "Farewell party"}


def test_routine_hire_is_confirmed_automatically(client):
    _, _, venue_id = seed_event()
    make_user("ann@x.com")
    login(client, "ann@x.com")
    r = post(client, "/hire", **hire_data(venue_id))
    assert r.status_code == 303 and r.headers["location"] == "/hire/my"
    assert "confirmed" in client.get("/hire/my").text


def test_clashing_hire_offers_alternatives(client):
    _, _, venue_id = seed_event()
    make_user("ann@x.com")
    make_user("bob@x.com")
    login(client, "ann@x.com")
    post(client, "/hire", **hire_data(venue_id))
    with TestClient(app) as bob:
        login(bob, "bob@x.com")
        r = post(bob, "/hire", **hire_data(venue_id))
        assert r.status_code == 200
        assert "Alternatives" in r.text and "Book this instead" in r.text


def test_hire_validation_errors(client):
    _, _, venue_id = seed_event()
    make_user("ann@x.com")
    login(client, "ann@x.com")
    bad = hire_data(venue_id, hours=-2)
    assert post(client, "/hire", **bad).status_code == 400           # end before start (refused by VenueAgent)
    assert post(client, "/hire", **{**hire_data(venue_id), "guests": "abc"}).status_code == 400
    assert post(client, "/hire", **hire_data(venue_id, days=-2)).status_code == 400   # in the past
