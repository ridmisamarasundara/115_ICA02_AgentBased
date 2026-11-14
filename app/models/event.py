from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Numeric, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._util import utcnow


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), index=True)  # concert, workshop, seminar, conference
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published | cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    venue = relationship("Venue", back_populates="events")
    categories = relationship("TicketCategory", back_populates="event", cascade="all, delete-orphan")


class TicketCategory(Base):
    """e.g. 'General' / 'VIP'. `sold` is only ever changed with an atomic UPDATE (see BookingAgent)."""
    __tablename__ = "ticket_categories"
    __table_args__ = (
        # Last line of defence against overselling, enforced by the database itself.
        CheckConstraint("sold >= 0 AND sold <= quantity", name="ck_sold_within_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False))
    quantity: Mapped[int] = mapped_column(Integer)
    sold: Mapped[int] = mapped_column(Integer, default=0)

    event = relationship("Event", back_populates="categories")
