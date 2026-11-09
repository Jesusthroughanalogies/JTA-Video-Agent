"""Posting slots, kept in US Eastern time (the audience), never in the time zone Matt is in.

The scheduler only has to run `jta-reels publish` every 10 minutes in any time zone. The code
decides whether a slot is due, so daylight saving and slot changes need no crontab edits.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc


@dataclass(frozen=True)
class Slot:
    day: dt.date        # local (Eastern) date
    number: int         # 1..4
    at: dt.datetime     # aware, local time zone

    @property
    def at_utc(self) -> dt.datetime:
        return self.at.astimezone(UTC)


def _parse(hhmm: str) -> dt.time:
    h, m = hhmm.split(":")
    return dt.time(int(h), int(m))


def slots_on(day: dt.date, slot_times: list[str], tz: str) -> list[Slot]:
    z = ZoneInfo(tz)
    return [Slot(day, i + 1, dt.datetime.combine(day, _parse(t), tzinfo=z)) for i, t in enumerate(slot_times)]


def local_day(now_utc: dt.datetime, tz: str) -> dt.date:
    return now_utc.astimezone(ZoneInfo(tz)).date()


def day_bounds_utc(day: dt.date, tz: str) -> tuple[dt.datetime, dt.datetime]:
    z = ZoneInfo(tz)
    start = dt.datetime.combine(day, dt.time(0), tzinfo=z)
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0), tzinfo=z)
    return start.astimezone(UTC), end.astimezone(UTC)


def due_slots(now_utc: dt.datetime, slot_times: list[str], tz: str, catchup_hours: float = 3) -> list[Slot]:
    """Slots whose time has come and that are still inside the catch-up window, oldest first.

    The window lets a run that was late (server reboot, outage) still post, without a
    morning reel turning up in the evening.
    """
    day = local_day(now_utc, tz)
    window = dt.timedelta(hours=catchup_hours)
    out = []
    for d in (day - dt.timedelta(days=1), day):          # a late-evening slot can run past midnight
        for s in slots_on(d, slot_times, tz):
            if s.at_utc <= now_utc < s.at_utc + window:
                out.append(s)
    return out
