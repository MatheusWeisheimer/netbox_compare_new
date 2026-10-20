"""When a comparison schedule runs next. Pure functions: no Django models, no database."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, time, timedelta, tzinfo


def next_occurrence(
    weekdays: Collection[int], time_of_day: time, after: datetime, tz: tzinfo
) -> datetime:
    """The first moment strictly after ``after`` that falls on one of ``weekdays`` (Monday is 0)
    at ``time_of_day`` in ``tz``.

    The wall-clock time is resolved per day in ``tz``, so daylight-saving changes don't shift
    it. Raises ``ValueError`` when ``weekdays`` is empty.
    """
    days = set(weekdays)
    if not days:
        raise ValueError("at least one weekday is required")
    local = after.astimezone(tz)
    for offset in range(8):
        day = local.date() + timedelta(days=offset)
        if day.weekday() in days:
            candidate = datetime.combine(day, time_of_day.replace(tzinfo=None), tzinfo=tz)
            if candidate > after:
                return candidate
    raise ValueError(f"invalid weekdays: {sorted(days)}")  # not reachable for 0-6
