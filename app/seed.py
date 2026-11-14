"""Demo data: three demo accounts, three venues and three sample events."""
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import User, Venue, Event, TicketCategory
from app.models._util import utcnow
from app.security import hash_password

DEMO_ACCOUNTS = [
    ("Admin User", "admin@eventsphere.test", "Admin@12345", "admin"),
    ("Gate Staff", "staff@eventsphere.test", "Staff@12345", "staff"),
    ("Demo Attendee", "attendee@eventsphere.test", "Attendee@12345", "attendee"),
]


def _at(days: int, hour: int):
    return (utcnow() + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)


def seed_demo(db: Session) -> bool:
    """Idempotent: does nothing if data already exists. Returns True if something was created."""
    created = False
    for name, email, password, role in DEMO_ACCOUNTS:
        if not db.query(User).filter_by(email=email).first():
            db.add(User(name=name, email=email, password_hash=hash_password(password), role=role))
            created = True

    if db.query(Venue).count() == 0:
        hall = Venue(name="Main Auditorium", location="University of Vavuniya, Block A", capacity=300,
                     description="Large auditorium with stage, sound system and tiered seating.",
                     hourly_rate=5000, open_for_hire=True)
        room = Venue(name="Seminar Room 1", location="University of Vavuniya, Block B", capacity=60,
                     description="Air-conditioned room with projector, ideal for workshops.",
                     hourly_rate=1500, open_for_hire=True)
        garden = Venue(name="Garden Pavilion", location="University of Vavuniya, Campus Garden", capacity=120,
                       description="Open-air pavilion for receptions and club meetings.",
                       hourly_rate=3000, open_for_hire=True)
        db.add_all([hall, room, garden])
        db.flush()
        samples = [
            (hall, "Spring Concert", "concert", _at(10, 18), 3, "An evening of live music by campus bands.",
             [("General", 1500, 200), ("VIP", 3500, 50)]),
            (room, "Python Workshop", "workshop", _at(5, 9), 3, "Hands-on beginner workshop. Bring a laptop.",
             [("Standard", 500, 40)]),
            (garden, "Tech Seminar", "seminar", _at(20, 14), 2, "Talks on AI and cloud careers.",
             [("Student", 0, 60), ("Public", 800, 40)]),
        ]
        for venue, title, category, start, hours, desc, cats in samples:
            ev = Event(title=title, category=category, venue_id=venue.id, start_time=start,
                       end_time=start + timedelta(hours=hours), description=desc, status="published")
            db.add(ev)
            db.flush()
            for cname, price, qty in cats:
                db.add(TicketCategory(event_id=ev.id, name=cname, price=price, quantity=qty))
        created = True
    db.commit()
    return created
