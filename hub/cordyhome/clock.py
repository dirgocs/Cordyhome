"""Relógio injetável: facilita testes de energia e agendamentos."""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo


class Clock:
    def now(self) -> float:
        return time.time()

    def local(self, tz: str, ts: float | None = None) -> datetime:
        return datetime.fromtimestamp(self.now() if ts is None else ts, ZoneInfo(tz))


class FakeClock(Clock):
    def __init__(self, start: float):
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds
