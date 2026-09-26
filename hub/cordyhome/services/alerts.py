"""Alertas: um registro por ocorrência, resolvido automaticamente quando a condição some."""

from __future__ import annotations

from ..db import Database
from ..events import EventBus

SEVERITIES = ("info", "warning", "critical")


class AlertService:
    def __init__(self, db: Database, bus: EventBus):
        self.db = db
        self.bus = bus

    def open(self, kind: str, message: str, *, device_id: int | None, severity: str, now: float):
        """Abre um alerta, a menos que já exista um aberto do mesmo tipo para o dispositivo."""
        existing = self.db.scalar(
            "SELECT id FROM alerts WHERE kind = ? AND device_id IS ? AND resolved_at IS NULL",
            (kind, device_id),
        )
        if existing:
            return existing
        cur = self.db.execute(
            "INSERT INTO alerts (device_id, kind, severity, message, created_at) "
            "VALUES (?,?,?,?,?)",
            (device_id, kind, severity, message, int(now)),
        )
        self.bus.publish("alerts")
        return cur.lastrowid

    def record(self, kind: str, message: str, *, device_id: int | None, severity: str, now: float):
        """Registra um evento pontual (ex.: comando falhou), já resolvido no ato."""
        self.db.execute(
            "INSERT INTO alerts (device_id, kind, severity, message, created_at, resolved_at) "
            "VALUES (?,?,?,?,?,?)",
            (device_id, kind, severity, message, int(now), int(now)),
        )
        self.bus.publish("alerts")

    def resolve(self, kind: str, *, device_id: int | None, now: float) -> None:
        cur = self.db.execute(
            "UPDATE alerts SET resolved_at = ? "
            "WHERE kind = ? AND device_id IS ? AND resolved_at IS NULL",
            (int(now), kind, device_id),
        )
        if cur.rowcount:
            self.bus.publish("alerts")

    def acknowledge(self, alert_id: int | None, now: float) -> None:
        if alert_id is None:
            self.db.execute(
                "UPDATE alerts SET acknowledged_at = ? WHERE acknowledged_at IS NULL", (int(now),)
            )
        else:
            self.db.execute(
                "UPDATE alerts SET acknowledged_at = COALESCE(acknowledged_at, ?) WHERE id = ?",
                (int(now), alert_id),
            )
        self.bus.publish("alerts")

    def unread_count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM alerts WHERE acknowledged_at IS NULL"))
