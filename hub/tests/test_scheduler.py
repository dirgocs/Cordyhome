from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from cordyhome.services.scheduler import due_key, next_run

TZ = ZoneInfo("America/Sao_Paulo")
THURSDAY = 1 << 4
WEEKDAYS = 0b0111110


def at(h, m, day=15):
    return datetime(2026, 1, day, h, m, 20, tzinfo=TZ)


def test_due_on_matching_minute_and_day():
    assert due_key("07:30", WEEKDAYS, None, at(7, 30)) == "2026-01-15 07:30"


def test_not_due_on_other_days():
    sunday = at(7, 30, day=18)
    assert due_key("07:30", WEEKDAYS, None, sunday) is None


def test_catches_up_one_missed_minute_but_never_twice():
    assert due_key("07:30", THURSDAY, None, at(7, 31)) == "2026-01-15 07:30"
    assert due_key("07:30", THURSDAY, "2026-01-15 07:30", at(7, 31)) is None
    assert due_key("07:30", THURSDAY, None, at(7, 33)) is None


def test_next_run_skips_to_allowed_day():
    nxt = next_run("07:30", 1 << 1, at(8, 0))  # só segunda-feira
    assert nxt is not None and nxt.weekday() == 0 and (nxt.hour, nxt.minute) == (7, 30)
