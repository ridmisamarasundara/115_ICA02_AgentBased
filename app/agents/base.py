"""Base class for all agents."""
from app.agents.bus import MessageBus, BROADCAST
from app.agents.messages import Message, Performative
from app.models import AgentState
from app.models._util import utcnow


class BaseAgent:
    name = "BaseAgent"
    listens_to_broadcast = False  # set True for reactive agents (e.g. NotificationAgent)

    def __init__(self, bus: MessageBus):
        self.bus = bus
        bus.register(self, listener=self.listens_to_broadcast)

    # ---- receiving -------------------------------------------------
    def handle(self, msg: Message, db) -> Message | None:
        """Dispatch on content['action'] (requests) or content['event'] (broadcasts)
        to a method called on_<name>(msg, db)."""
        key = msg.content.get("action") or msg.content.get("event")
        method = getattr(self, f"on_{key}", None) if key else None
        if method is None:
            return msg.reply(Performative.FAILURE, {"reason": f"{self.name} cannot handle '{key}'"})
        return method(msg, db)

    # ---- sending ---------------------------------------------------
    def send(self, receiver: str, performative: Performative, content: dict, db,
             conversation_id: str | None = None) -> Message | None:
        kwargs = {"conversation_id": conversation_id} if conversation_id else {}
        msg = Message(sender=self.name, receiver=receiver, performative=performative,
                      content=content, **kwargs)
        return self.bus.send(msg, db)

    def broadcast(self, event: str, content: dict, db, conversation_id: str | None = None):
        return self.send(BROADCAST, Performative.INFORM, {"event": event, **content}, db, conversation_id)

    # ---- persistent beliefs (state) -----------------------------------
    def get_state(self, db, key: str, default=None):
        row = db.query(AgentState).filter_by(agent=self.name, key=key).first()
        return row.value["v"] if row else default

    def set_state(self, db, key: str, value):
        row = db.query(AgentState).filter_by(agent=self.name, key=key).first()
        if row:
            row.value = {"v": value}
            row.updated_at = utcnow()
        else:
            db.add(AgentState(agent=self.name, key=key, value={"v": value}))
        db.flush()
