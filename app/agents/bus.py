"""The message bus: the ONLY way agents talk to each other.

* Every message is written to MessageLog (traceability).
* Direct message  -> delivered to the receiver's handle(); its return value is the reply.
* Broadcast ("ALL") -> delivered to every agent registered as a listener (reactive behaviour).
"""
from app.agents.messages import Message, Performative
from app.models import MessageLog

BROADCAST = "ALL"


class MessageBus:
    def __init__(self):
        self._agents = {}      # name -> agent
        self._listeners = set()

    def register(self, agent, listener: bool = False):
        self._agents[agent.name] = agent
        if listener:
            self._listeners.add(agent.name)

    def _log(self, msg: Message, db):
        db.add(MessageLog(
            conversation_id=msg.conversation_id,
            sender=msg.sender,
            receiver=msg.receiver,
            performative=msg.performative.value,
            content=msg.model_dump(mode="json")["content"],
        ))
        db.flush()

    def send(self, msg: Message, db) -> Message | None:
        self._log(msg, db)

        if msg.receiver == BROADCAST:
            for name in sorted(self._listeners):
                if name != msg.sender:
                    self._agents[name].handle(msg, db)
            return None

        agent = self._agents.get(msg.receiver)
        if agent is None:
            failure = Message(
                sender="MessageBus", receiver=msg.sender,
                performative=Performative.FAILURE,
                content={"reason": f"unknown receiver '{msg.receiver}'"},
                conversation_id=msg.conversation_id,
            )
            self._log(failure, db)
            return failure

        reply = agent.handle(msg, db)
        if reply is not None:
            self._log(reply, db)
        return reply


# One shared bus for the whole application
bus = MessageBus()
