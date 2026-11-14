import pytest
from pydantic import ValidationError

from app.agents.base import BaseAgent
from app.agents.bus import MessageBus, BROADCAST
from app.agents.messages import Message, Performative
from app.models import MessageLog


class EchoAgent(BaseAgent):
    name = "EchoAgent"

    def on_echo(self, msg, db):
        count = self.get_state(db, "count", 0) + 1
        self.set_state(db, "count", count)
        return msg.reply(Performative.AGREE, {"echo": msg.content["text"], "count": count})


class ListenerAgent(BaseAgent):
    name = "ListenerAgent"
    listens_to_broadcast = True

    def __init__(self, bus):
        super().__init__(bus)
        self.seen = []

    def on_ping(self, msg, db):
        self.seen.append(msg.content)


def test_request_gets_reply_and_both_are_logged_with_same_conversation_id(db):
    bus = MessageBus()
    EchoAgent(bus)
    req = Message(sender="Tester", receiver="EchoAgent", performative=Performative.REQUEST,
                  content={"action": "echo", "text": "hi"})
    reply = bus.send(req, db)

    assert reply.performative == Performative.AGREE
    assert reply.content["echo"] == "hi"
    rows = db.query(MessageLog).filter_by(conversation_id=req.conversation_id).all()
    assert len(rows) == 2


def test_refuse_without_reason_is_rejected():
    with pytest.raises(ValidationError):
        Message(sender="A", receiver="B", performative=Performative.REFUSE, content={})


def test_propose_needs_alternatives():
    with pytest.raises(ValidationError):
        Message(sender="A", receiver="B", performative=Performative.PROPOSE,
                content={"reason": "clash"})


def test_unknown_receiver_returns_failure(db):
    bus = MessageBus()
    msg = Message(sender="Tester", receiver="Nobody", performative=Performative.REQUEST,
                  content={"action": "x"})
    assert bus.send(msg, db).performative == Performative.FAILURE


def test_unsupported_action_returns_failure(db):
    bus = MessageBus()
    EchoAgent(bus)
    msg = Message(sender="Tester", receiver="EchoAgent", performative=Performative.REQUEST,
                  content={"action": "dance"})
    assert bus.send(msg, db).performative == Performative.FAILURE


def test_broadcast_reaches_listener(db):
    bus = MessageBus()
    listener = ListenerAgent(bus)
    EchoAgent(bus)
    msg = Message(sender="Tester", receiver=BROADCAST, performative=Performative.INFORM,
                  content={"event": "ping", "n": 1})
    bus.send(msg, db)
    assert len(listener.seen) == 1


def test_agent_state_survives_restart(db):
    bus1 = MessageBus()
    EchoAgent(bus1)
    req = lambda: Message(sender="T", receiver="EchoAgent", performative=Performative.REQUEST,
                          content={"action": "echo", "text": "x"})
    bus1.send(req(), db)
    db.commit()

    # "restart": brand-new bus and agent object, same database
    bus2 = MessageBus()
    EchoAgent(bus2)
    assert bus2.send(req(), db).content["count"] == 2
