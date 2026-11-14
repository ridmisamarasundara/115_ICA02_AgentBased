import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Event, TicketCategory, User, Venue
from app.models._util import utcnow
from app.security import hash_password

PW = "Passw0rd!"


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


def csrf(client, path="/login"):
    html = client.get(path).text
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def make_user(email, role="attendee", name=None):
    with SessionLocal() as db:
        u = User(name=name or role.title(), email=email, password_hash=hash_password(PW), role=role)
        db.add(u)
        db.commit()
        return u.id


def login(client, email, password=PW):
    return client.post("/login", data={"email": email, "password": password, "csrf_token": csrf(client)},
                       follow_redirects=False)


def post(client, path, **data):
    data["csrf_token"] = csrf(client, "/login")      # a logged-in user is redirected to a page that has the token
    return client.post(path, data=data, follow_redirects=False)


def seed_event(days=10, quantity=10, price=500, title="Concert", category="concert", status="published",
               venue_name="Main Hall", capacity=500, rate=1000):
    with SessionLocal() as db:
        venue = Venue(name=venue_name, location="Campus", capacity=capacity, hourly_rate=rate, open_for_hire=True)
        db.add(venue)
        db.flush()
        start = utcnow() + timedelta(days=days)
        ev = Event(title=title, category=category, venue_id=venue.id, start_time=start,
                   end_time=start + timedelta(hours=3), description=f"About {title}", status=status)
        db.add(ev)
        db.flush()
        cat = TicketCategory(event_id=ev.id, name="General", price=price, quantity=quantity)
        db.add(cat)
        db.commit()
        return ev.id, cat.id, venue.id
