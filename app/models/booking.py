from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._util import utcnow


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("ticket_categories.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False))
    status: Mapped[str] = mapped_column(String(20), default="confirmed")  # confirmed | cancelled
    refund_amount: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    tickets = relationship("Ticket", back_populates="booking")
    payment = relationship("Payment", back_populates="booking", uselist=False)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # secrets.token_urlsafe(24)
    status: Mapped[str] = mapped_column(String(20), default="valid")  # valid | used | cancelled
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scan_count: Mapped[int] = mapped_column(Integer, default=0)

    booking = relationship("Booking", back_populates="tickets")


class Payment(Base):
    """Simulated payment: only a reference is stored, never card details."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False))
    status: Mapped[str] = mapped_column(String(20), default="paid")  # paid | refunded | partially_refunded
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    booking = relationship("Booking", back_populates="payment")
