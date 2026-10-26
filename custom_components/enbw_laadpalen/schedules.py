"""Refresh schedules per station (pure logic, no Home Assistant imports).

Each schedule is a list of (hours, minutes) combinations at which to refresh.
``None`` means: never refresh automatically.
"""

from __future__ import annotations

ALL_HOURS = list(range(24))
EVERY_5 = list(range(0, 60, 5))
EVERY_15 = [0, 15, 30, 45]
EVERY_30 = [0, 30]
MORNING = [6, 7, 8]  # 06:00 to 09:00 (09:00 itself is added by _window)
EVENING = [16, 17, 18]  # 16:00 to 19:00

Spec = list[tuple[list[int], list[int]]]


def _window(hours: list[int], minutes: list[int]) -> Spec:
    """Window including its end point (e.g. 09:00)."""
    return [(hours, minutes), ([hours[-1] + 1], [0])]


SCHEDULES: dict[str, Spec | None] = {
    "never": None,
    "daily": [([6], [0])],
    "hourly": [(ALL_HOURS, [0])],
    "every_30_min_06_09": _window(MORNING, EVERY_30),
    "every_30_min_16_19": _window(EVENING, EVERY_30),
    "every_15_min": [(ALL_HOURS, EVERY_15)],
    "every_5_min": [(ALL_HOURS, EVERY_5)],
    "every_5_min_rush": _window(MORNING, EVERY_5) + _window(EVENING, EVERY_5),
}
DEFAULT_SCHEDULE = "never"  # refresh button / proximity / own automations only


# Refresh interval while someone is in the zone (minutes); None = on entry only
ZONE_INTERVALS: dict[str, int | None] = {
    "on_entry": None,
    "every_2_min": 2,
    "every_5_min": 5,
    "every_10_min": 10,
    "every_15_min": 15,
}
DEFAULT_ZONE_INTERVAL = "every_5_min"

# How long a visit keeps refreshing (minutes); None = unlimited
ZONE_STOP_AFTER: dict[str, int | None] = {
    "10_min": 10,
    "30_min": 30,
    "60_min": 60,
    "120_min": 120,
    "unlimited": None,
}
DEFAULT_ZONE_STOP_AFTER = "30_min"


def fires_at(key: str, hour: int, minute: int) -> bool:
    spec = SCHEDULES.get(key)
    if not spec:
        return False
    return any(hour in h and minute in m for h, m in spec)
