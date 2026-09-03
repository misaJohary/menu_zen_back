from datetime import datetime, time, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel

from app.schemas.restaurant_schemas import OpeningHours


class NextOpening(BaseModel):
    day: str
    time: str


_WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def compute_open_status(
    opening_hours: Optional[OpeningHours],
    now_utc: Optional[datetime] = None,
) -> Tuple[bool, Optional[NextOpening]]:
    if opening_hours is None or not opening_hours.periods:
        return False, None

    try:
        tz = ZoneInfo(opening_hours.timezone)
    except ZoneInfoNotFoundError:
        return False, None

    if now_utc is None:
        now_utc = datetime.now(tz=timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_local = now_utc.astimezone(tz)
    today_idx = now_local.weekday()
    current_t = now_local.time()

    periods_by_day: dict[int, list] = {}
    for period in opening_hours.periods:
        slots = sorted(period.slots, key=lambda s: time.fromisoformat(s.open))
        periods_by_day[period.day] = slots

    today_slots = periods_by_day.get(today_idx, [])
    for slot in today_slots:
        open_t = time.fromisoformat(slot.open)
        close_t = time.fromisoformat(slot.close)
        if open_t <= current_t < close_t:
            return True, None

    for slot in today_slots:
        open_t = time.fromisoformat(slot.open)
        if open_t > current_t:
            return False, NextOpening(day="today", time=slot.open)

    for offset in range(1, 8):
        idx = (today_idx + offset) % 7
        slots = periods_by_day.get(idx)
        if not slots:
            continue
        first = slots[0]
        if offset == 1:
            day_label = "tomorrow"
        else:
            day_label = _WEEKDAY_NAMES[idx]
        return False, NextOpening(day=day_label, time=first.open)

    return False, None


