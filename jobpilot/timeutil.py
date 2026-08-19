"""Shared time helpers. Fixed +07:00 (Asia/Ho_Chi_Minh, no DST) — avoids a
tzdata dependency on Windows and keeps crawl/API timestamps consistent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))


def vn_now() -> datetime:
    """Current time in Vietnam (tz-aware)."""
    return datetime.now(VN_TZ)


def as_aware(value: datetime | None) -> datetime | None:
    """Attach ``VN_TZ`` to a naive datetime; leave an aware one alone.

    Needed wherever a stored timestamp meets a computed one. Postgres returns
    these columns tz-aware while SQLite returns them naive, so comparing a value
    read from the database against ``vn_now()`` raises "can't compare
    offset-naive and offset-aware datetimes" — on the fixture database only,
    which is the worst place for it to hide. Production stays upright purely
    because both sides come from the same connection, right up until one caller
    passes a time it computed itself.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=VN_TZ)
