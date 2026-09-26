"""Regras de disparo dos agendamentos (funções puras, testáveis)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
ALL_DAYS = 0b1111111  # bit 0 = domingo … bit 6 = sábado


def weekday_bit(dt: datetime) -> int:
    # Python: segunda = 0 … domingo = 6. Cordyhome: domingo = 0 … sábado = 6.
    return 1 << ((dt.weekday() + 1) % 7)


def minute_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def due_key(time_str: str, days: int, last_run_key: str | None, now: datetime) -> str | None:
    """Retorna a chave do minuto a executar, ou None.

    Olha o minuto atual e o anterior, para não perder disparos se um ciclo do agendador
    atrasar; `last_run_key` impede execuções duplicadas.
    """
    for candidate in (now, now - timedelta(minutes=1)):
        if candidate.strftime("%H:%M") != time_str or not days & weekday_bit(candidate):
            continue
        key = minute_key(candidate)
        if key != last_run_key:
            return key
    return None


def next_run(time_str: str, days: int, now: datetime) -> datetime | None:
    if not days:
        return None
    hour, minute = map(int, time_str.split(":"))
    for offset in range(8):
        day = now + timedelta(days=offset)
        candidate = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now and days & weekday_bit(candidate):
            return candidate
    return None
