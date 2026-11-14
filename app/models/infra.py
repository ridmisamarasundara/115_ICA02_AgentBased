from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._util import utcnow


class MessageLog(Base):
    """Every agent message is stored here (traceability, shown on the admin dashboard)."""
    __tablename__ = "message_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(40), index=True)
    sender: Mapped[str] = mapped_column(String(50))
    receiver: Mapped[str] = mapped_column(String(50))
    performative: Mapped[str] = mapped_column(String(20))
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentState(Base):
    """Persistent beliefs of each agent (counters, scan history, offer expiry...). Survives restarts."""
    __tablename__ = "agent_state"
    __table_args__ = (UniqueConstraint("agent", "key", name="uq_agent_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(50), index=True)
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[dict] = mapped_column(JSON, default=dict)  # stored as {"v": <anything>}
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    """Created by NotificationAgent."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
