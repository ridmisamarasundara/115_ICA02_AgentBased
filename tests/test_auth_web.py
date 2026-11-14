import re

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Notification, User
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


def register(client, **overrides):
    data = {"name": "Nimal Perera", "email": "nimal@example.com", "password": PW, "confirm": PW}
    data.update(overrides)
    data["csrf_token"] = csrf(client, "/register")
    return client.post("/register", data=data, follow_redirects=False)


def test_registration_stores_a_hashed_password(client):
    r = register(client)
    assert r.status_code == 303
    with SessionLocal() as db:
        user = db.query(User).filter_by(email="nimal@example.com").one()
    assert user.password_hash != PW
    assert user.password_hash.startswith("$2")          # bcrypt


def test_registration_validates_input(client):
    assert register(client, password="short", confirm="short").status_code == 400
    assert register(client, password="NoNumbersHere", confirm="NoNumbersHere").status_code == 400
    assert register(client, confirm="Different1").status_code == 400
    assert register(client, email="not-an-email").status_code == 400
    assert register(client).status_code == 303
    client.cookies.clear()
    assert register(client).status_code == 400          # duplicate email


def test_role_cannot_be_chosen_at_registration(client):
    register(client, role="admin")
    with SessionLocal() as db:
        assert db.query(User).filter_by(email="nimal@example.com").one().role == "attendee"


def test_login_success_and_failure(client):
    make_user("admin@x.com", "admin")
    bad = login(client, "admin@x.com", "wrong-password")
    assert bad.status_code == 400 and "Invalid" in bad.text
    ok = login(client, "admin@x.com")
    assert ok.status_code == 303 and ok.headers["location"] == "/admin"


def test_post_without_csrf_token_is_rejected(client):
    make_user("a@x.com")
    r = client.post("/login", data={"email": "a@x.com", "password": PW}, follow_redirects=False)
    assert r.status_code == 403


def test_anonymous_user_is_sent_to_login(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_admin_pages_enforce_roles(client):
    make_user("att@x.com", "attendee")
    make_user("staff@x.com", "staff")
    make_user("admin@x.com", "admin")

    login(client, "att@x.com")
    assert client.get("/admin").status_code == 403
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "staff@x.com")
    assert client.get("/admin").status_code == 403
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "admin@x.com")
    assert client.get("/admin").status_code == 200


def test_scanner_is_for_staff_and_admin_only(client):
    make_user("att@x.com", "attendee")
    make_user("staff@x.com", "staff")
    login(client, "att@x.com")
    assert client.get("/staff/scan").status_code == 403
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "staff@x.com")
    assert client.get("/staff/scan").status_code == 200


def test_logout_ends_the_session(client):
    make_user("att@x.com")
    login(client, "att@x.com")
    assert client.get("/notifications").status_code == 200
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    assert client.get("/notifications", follow_redirects=False).status_code == 303


def test_notifications_page_shows_and_marks_read(client):
    uid = make_user("att@x.com")
    with SessionLocal() as db:
        db.add(Notification(user_id=uid, message="Booking #1 confirmed"))
        db.commit()
    login(client, "att@x.com")
    assert "Booking #1 confirmed" in client.get("/notifications").text
    with SessionLocal() as db:
        assert db.query(Notification).filter_by(user_id=uid, is_read=False).count() == 0
