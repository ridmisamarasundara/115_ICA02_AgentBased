from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC datetime (works the same on SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
