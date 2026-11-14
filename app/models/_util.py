from datetime import datetime, timedelta, timezone

from app.config import TZ_OFFSET_MINUTES


def utcnow() -> datetime:
    """'Now' as a naive datetime in the venue's local time (UTC + TZ_OFFSET_MINUTES).

    The name is kept for history; every date in the system (events, holds, refunds) is local
    venue time, so comparisons are consistent on any server timezone."""
    return (datetime.now(timezone.utc) + timedelta(minutes=TZ_OFFSET_MINUTES)).replace(tzinfo=None)
