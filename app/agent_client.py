"""How the web layer talks to the agents: it sends a REQUEST message on the bus and gets the reply.
The web routes never call agent functions directly."""
from app.agents.bus import bus
from app.agents.messages import Message, Performative


def ask(db, receiver: str, action: str, sender: str = "WebApp", **content):
    msg = Message(sender=sender, receiver=receiver, performative=Performative.REQUEST,
                  content={"action": action, **content})
    try:
        reply = bus.send(msg, db)
        db.commit()                 # keeps the message log, counters and state even for refusals
    except Exception:
        db.rollback()
        raise
    return reply
