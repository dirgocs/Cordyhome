"""Medição e agregação de energia.

A cada leitura de potência integramos a energia pelo método do trapézio entre duas leituras
consecutivas. Os totais vão para buckets de 1 minuto (detalhe recente, 14 dias) e de 1 hora
(histórico permanente). Relatórios por dia/mês partem dos buckets horários.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..db import Database

MINUTE_RETENTION_DAYS = 14


@dataclass
class _Sample:
    ts: float
    watts: float


@dataclass
class _Bucket:
    minute: int
    wh: float = 0.0
    watt_sum: float = 0.0
    count: int = 0
    max_w: float = 0.0


@dataclass
class EnergyMeter:
    db: Database
    max_gap_sec: float = 60.0
    _last: dict[int, _Sample] = field(default_factory=dict)
    _buckets: dict[int, _Bucket] = field(default_factory=dict)

    def record(self, device_id: int, ts: float, watts: float | None) -> None:
        """Registra uma leitura; `None` significa aparelho offline (interrompe a integração)."""
        if watts is None:
            self._last.pop(device_id, None)
            return
        watts = max(0.0, float(watts))
        minute = int(ts // 60) * 60
        bucket = self._buckets.get(device_id)
        if bucket is not None and bucket.minute != minute:
            self._flush_bucket(device_id, bucket)
            bucket = None
        if bucket is None:
            bucket = self._buckets[device_id] = _Bucket(minute=minute)

        prev = self._last.get(device_id)
        if prev is not None and ts > prev.ts:
            # Lacunas longas (hub parado, falhas) não são extrapoladas.
            dt = min(ts - prev.ts, self.max_gap_sec)
            bucket.wh += (prev.watts + watts) / 2 * dt / 3600
        bucket.watt_sum += watts
        bucket.count += 1
        bucket.max_w = max(bucket.max_w, watts)
        self._last[device_id] = _Sample(ts=ts, watts=watts)

    def flush(self) -> None:
        for device_id, bucket in list(self._buckets.items()):
            self._flush_bucket(device_id, bucket)
        self._buckets.clear()

    def forget(self, device_id: int) -> None:
        self._last.pop(device_id, None)
        self._buckets.pop(device_id, None)

    def pending_wh(self, device_id: int) -> float:
        bucket = self._buckets.get(device_id)
        return bucket.wh if bucket else 0.0

    def _flush_bucket(self, device_id: int, bucket: _Bucket) -> None:
        if bucket.count == 0:
            return
        avg = bucket.watt_sum / bucket.count
        hour = bucket.minute - bucket.minute % 3600
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO energy_minute (device_id, ts, wh, avg_w, max_w) VALUES (?,?,?,?,?) "
                "ON CONFLICT(device_id, ts) DO UPDATE SET wh = wh + excluded.wh, "
                "avg_w = excluded.avg_w, max_w = MAX(max_w, excluded.max_w)",
                (device_id, bucket.minute, bucket.wh, avg, bucket.max_w),
            )
            self.db.execute(
                "INSERT INTO energy_hour (device_id, ts, wh) VALUES (?,?,?) "
                "ON CONFLICT(device_id, ts) DO UPDATE SET wh = wh + excluded.wh",
                (device_id, hour, bucket.wh),
            )
        bucket.wh = bucket.watt_sum = bucket.max_w = 0.0
        bucket.count = 0

    def prune(self, now: float) -> None:
        cutoff = int(now) - MINUTE_RETENTION_DAYS * 86400
        self.db.execute("DELETE FROM energy_minute WHERE ts < ?", (cutoff,))


# ---------------------------------------------------------------------------------------------
# Relatórios

RANGES = ("today", "yesterday", "7d", "30d", "month", "12m")


@dataclass
class Period:
    start: datetime
    end: datetime
    bucket: str  # "hour" | "day" | "month"


def period_for(range_key: str, tz: str, now: float) -> Period:
    zone = ZoneInfo(tz)
    local_now = datetime.fromtimestamp(now, zone)
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_key == "today":
        return Period(today, today + timedelta(days=1), "hour")
    if range_key == "yesterday":
        return Period(today - timedelta(days=1), today, "hour")
    if range_key == "7d":
        return Period(today - timedelta(days=6), today + timedelta(days=1), "day")
    if range_key == "30d":
        return Period(today - timedelta(days=29), today + timedelta(days=1), "day")
    if range_key == "month":
        start = today.replace(day=1)
        return Period(start, _add_months(start, 1), "day")
    if range_key == "12m":
        start = _add_months(today.replace(day=1), -11)
        return Period(start, _add_months(today.replace(day=1), 1), "month")
    raise ValueError(f"Período inválido: {range_key}")


def _add_months(dt: datetime, months: int) -> datetime:
    index = dt.month - 1 + months
    return dt.replace(year=dt.year + index // 12, month=index % 12 + 1, day=1)


def _bucket_starts(period: Period) -> list[datetime]:
    starts: list[datetime] = []
    cursor = period.start
    while cursor < period.end:
        starts.append(cursor)
        if period.bucket == "hour":
            # Soma em UTC para atravessar mudanças de horário corretamente.
            cursor = datetime.fromtimestamp(cursor.timestamp() + 3600, cursor.tzinfo)
        elif period.bucket == "day":
            cursor = (cursor + timedelta(days=1)).replace(hour=0)
        else:
            cursor = _add_months(cursor, 1)
    return starts


def _bucket_key(dt: datetime, bucket: str) -> datetime:
    if bucket == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def energy_report(
    db: Database,
    meter: EnergyMeter,
    *,
    range_key: str,
    tz: str,
    now: float,
    tariff: float,
    device_ids: list[int] | None = None,
) -> dict:
    period = period_for(range_key, tz, now)
    zone = ZoneInfo(tz)
    start_ts, end_ts = int(period.start.timestamp()), int(period.end.timestamp())

    params: list = [start_ts, end_ts]
    device_filter = ""
    if device_ids is not None:
        if not device_ids:
            device_ids = [-1]
        device_filter = f" AND device_id IN ({','.join('?' * len(device_ids))})"
        params.extend(device_ids)
    rows = db.all(
        f"SELECT device_id, ts, wh FROM energy_hour WHERE ts >= ? AND ts < ?{device_filter}",
        params,
    )

    series_index = {start: 0.0 for start in _bucket_starts(period)}
    per_device: dict[int, float] = {}

    def add(device_id: int, ts: float, wh: float) -> None:
        key = _bucket_key(datetime.fromtimestamp(ts, zone), period.bucket)
        if key in series_index:
            series_index[key] += wh
        per_device[device_id] = per_device.get(device_id, 0.0) + wh

    for row in rows:
        add(row["device_id"], row["ts"], row["wh"])
    # Energia do minuto corrente ainda não gravada no banco.
    if start_ts <= now < end_ts:
        for device_id, bucket in meter._buckets.items():
            if device_ids is None or device_id in device_ids:
                add(device_id, now, bucket.wh)

    total_wh = sum(per_device.values())
    elapsed = max(0.0, min(now, end_ts) - start_ts)
    duration = end_ts - start_ts
    projection = None
    if range_key == "month" and elapsed > 6 * 3600:
        projection = total_wh / elapsed * duration / 1000

    return {
        "range": range_key,
        "bucket": period.bucket,
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "total_kwh": total_wh / 1000,
        "cost": total_wh / 1000 * tariff,
        "projected_kwh": projection,
        "projected_cost": projection * tariff if projection is not None else None,
        "series": [
            {"start": start.isoformat(), "kwh": wh / 1000} for start, wh in series_index.items()
        ],
        "devices": [
            {"device_id": device_id, "kwh": wh / 1000, "cost": wh / 1000 * tariff}
            for device_id, wh in sorted(per_device.items(), key=lambda kv: -kv[1])
        ],
    }


def power_history(db: Database, device_id: int, since: float) -> list[dict]:
    rows = db.all(
        "SELECT ts, avg_w, max_w FROM energy_minute WHERE device_id = ? AND ts >= ? ORDER BY ts",
        (device_id, int(since)),
    )
    return [{"ts": r["ts"], "avg_w": r["avg_w"], "max_w": r["max_w"]} for r in rows]


def total_power_history(db: Database, since: float) -> list[dict]:
    rows = db.all(
        "SELECT ts, SUM(avg_w) AS w FROM energy_minute WHERE ts >= ? GROUP BY ts ORDER BY ts",
        (int(since),),
    )
    return [{"ts": r["ts"], "w": r["w"]} for r in rows]
