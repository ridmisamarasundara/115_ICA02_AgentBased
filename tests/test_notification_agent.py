from app.agents.bus import MessageBus, BROADCAST
from app.agents.messages import Message, Performative as P
from app.agents.notification_agent import NotificationAgent
from app.models import Notification, User


def test_broadcast_event_becomes_user_notification(db):
    user = User(name="Ann", email="a@x.com", password_hash="x")
    db.add(user)
    db.commit()
    bus = MessageBus()
    agent = NotificationAgent(bus)

    bus.send(Message(sender="BookingAgent", receiver=BROADCAST, performative=P.INFORM,
                     content={"event": "hire_confirmed", "user_id": user.id,
                              "venue_name": "Main Hall", "date": "01 Dec 2026 10:00", "price": "3,000.00"}), db)

    note = db.query(Notification).filter_by(user_id=user.id).one()
    assert "Main Hall" in note.message
    assert agent.get_state(db, "notifications_created") == 1


def test_unknown_event_is_ignored(db):
    bus = MessageBus()
    NotificationAgent(bus)
    bus.send(Message(sender="X", receiver=BROADCAST, performative=P.INFORM,
                     content={"event": "mystery", "user_id": 1}), db)
    assert db.query(Notification).count() == 0
