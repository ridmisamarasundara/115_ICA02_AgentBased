"""Structured agent messages (FIPA-style performatives)."""
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class Performative(str, Enum):
    REQUEST = "REQUEST"
    AGREE = "AGREE"
    REFUSE = "REFUSE"
    PROPOSE = "PROPOSE"
    INFORM = "INFORM"
    FAILURE = "FAILURE"


def new_conversation_id() -> str:
    return uuid4().hex[:12]


class Message(BaseModel):
    sender: str
    receiver: str
    performative: Performative
    content: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str = Field(default_factory=new_conversation_id)

    @model_validator(mode="after")
    def _enforce_rules(self):
        # Rule: every REFUSE / PROPOSE / FAILURE must carry a reason.
        if self.performative in (Performative.REFUSE, Performative.PROPOSE, Performative.FAILURE):
            if not self.content.get("reason"):
                raise ValueError(f"{self.performative.value} must include a 'reason'")
        # Rule: a PROPOSE must contain usable alternatives.
        if self.performative == Performative.PROPOSE and not self.content.get("alternatives"):
            raise ValueError("PROPOSE must include a non-empty 'alternatives' list")
        return self

    def reply(self, performative: Performative, content: dict | None = None) -> "Message":
        """Build a reply in the same conversation with sender/receiver swapped."""
        return Message(
            sender=self.receiver,
            receiver=self.sender,
            performative=performative,
            content=content or {},
            conversation_id=self.conversation_id,
        )
