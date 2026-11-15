import re

from tests.web_helpers import client, login, make_user, post, seed_event  # noqa: F401


def test_home_page_has_the_mobile_layout(client):
    seed_event(title="Spring Concert")
    page = client.get("/").text
    assert 'name="viewport"' in page and "width=device-width" in page
    assert "Book Your Next Experience" in page
    for chip in ("Concerts", "Workshops", "Conferences", "Private Hire"):
        assert chip in page
    assert "es-tabbar" in page and "Book Now" in page


def test_free_events_show_free_instead_of_a_price(client):
    seed_event(title="Free Talk", price=0)
    assert "Free" in client.get("/").text


def test_profile_requires_login_and_shows_account_details(client):
    anonymous = client.get("/profile", follow_redirects=False)
    assert anonymous.status_code == 303 and anonymous.headers["location"].startswith("/login")
    make_user("ann@x.com", name="Ann Perera")
    login(client, "ann@x.com")
    page = client.get("/profile").text
    assert "Ann Perera" in page and "ann@x.com" in page and "Logout" in page


def test_bottom_tabs_depend_on_the_role(client):
    make_user("att@x.com", "attendee")
    login(client, "att@x.com")
    home = client.get("/").text
    assert "My Tickets" in home and 'href="/admin"' not in home and 'href="/staff/scan"' not in home
    client.post("/logout", data={"csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', home).group(1)})

    make_user("admin@x.com", "admin")
    login(client, "admin@x.com")
    assert 'href="/admin"' in client.get("/").text


def test_ticket_card_shows_ticket_id_and_scan_label(client):
    ev_id, cat_id, _ = seed_event()
    make_user("ann@x.com")
    login(client, "ann@x.com")
    location = post(client, f"/events/{ev_id}/book", category_id=cat_id, quantity=1).headers["location"]
    page = client.get(location).text
    assert "SCAN FOR ENTRY" in page and f"ES-{ev_id}-" in page and "View event details" in page


def test_home_has_faq_footer_and_cream_section(client):
    page = client.get("/").text
    assert "Frequently Asked Questions" in page and "es-footer" in page and "Find the Perfect Space" in page
    assert "What is the refund policy?" in page


def test_stylesheet_uses_the_espresso_amber_palette_and_serif_headings(client):
    css = client.get("/static/css/style.css").text
    assert "#E0A030" in css and "#2A1D15" in css and "Cormorant Garamond" in css
