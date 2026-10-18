"""Orquestra o estado dos dispositivos: polling, comandos, energia, alertas e agendamentos."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sqlite3
from typing import Any

from ..adapters.base import Adapter, AdapterError, DeviceReading, DeviceRef
from ..clock import Clock
from ..db import Database
from ..events import EventBus
from ..settings import SettingsStore
from .alerts import AlertService
from .energy import EnergyMeter
from .scheduler import due_key

log = logging.getLogger(__name__)

HIGH_POWER_RESOLVE_RATIO = 0.9
LAN_RESCAN_INTERVAL = 600


class DeviceNotFound(Exception):
    pass


def device_out(row: sqlite3.Row) -> dict[str, Any]:
    """Representação pública do dispositivo (nunca expõe a chave local)."""
    cfg = json.loads(row["config"] or "{}")
    power = row["power_w"] if row["online"] else None
    measured = power is not None
    if not measured and row["online"] and row["is_on"] and row["nominal_watts"]:
        power = row["nominal_watts"]
    return {
        "id": row["id"],
        "name": row["name"],
        "room_id": row["room_id"],
        "kind": row["kind"],
        "adapter": row["adapter"],
        "enabled": bool(row["enabled"]),
        "sort_order": row["sort_order"],
        "online": bool(row["online"]),
        "is_on": None if row["is_on"] is None else bool(row["is_on"]),
        "power_w": power,
        "power_estimated": not measured and power is not None,
        "voltage_v": row["voltage_v"],
        "current_a": row["current_a"],
        "last_seen": row["last_seen"],
        "last_error": row["last_error"],
        "nominal_watts": row["nominal_watts"],
        "power_alert_watts": row["power_alert_watts"],
        "confirm_off": bool(row["confirm_off"]),
        "info": {
            "ip": cfg.get("ip"),
            "protocol_version": cfg.get("version"),
            "product_name": cfg.get("product_name"),
            "has_energy_meter": bool((cfg.get("dp_map") or {}).get("power"))
            or row["adapter"] == "simulator",
        },
    }


class Hub:
    def __init__(
        self,
        db: Database,
        settings: SettingsStore,
        bus: EventBus,
        adapters: dict[str, Adapter],
        clock: Clock | None = None,
    ):
        self.db = db
        self.settings = settings
        self.bus = bus
        self.adapters = adapters
        self.clock = clock or Clock()
        self.alerts = AlertService(db, bus)
        self.meter = EnergyMeter(db)
        self._tasks: list[asyncio.Task] = []
        self._refresh_tasks: set[asyncio.Task] = set()
        self._last_rescan = 0.0
        self.lan_rescan = None  # callback injetado pela integração Tuya

    # ------------------------------------------------------------------ ciclo de vida

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._poll_loop(), name="poll"),
            asyncio.create_task(self._schedule_loop(), name="schedules"),
            asyncio.create_task(self._housekeeping_loop(), name="housekeeping"),
        ]

    async def stop(self) -> None:
        for task in [*self._tasks, *self._refresh_tasks]:
            task.cancel()
        await asyncio.gather(*self._tasks, *self._refresh_tasks, return_exceptions=True)
        self.meter.flush()

    # ------------------------------------------------------------------ consultas

    def row(self, device_id: int) -> sqlite3.Row:
        row = self.db.one("SELECT * FROM devices WHERE id = ?", (device_id,))
        if row is None:
            raise DeviceNotFound(device_id)
        return row

    def device(self, device_id: int) -> dict[str, Any]:
        return device_out(self.row(device_id))

    def devices(self) -> list[dict[str, Any]]:
        rows = self.db.all("SELECT * FROM devices ORDER BY sort_order, name COLLATE NOCASE")
        return [device_out(r) for r in rows]

    @staticmethod
    def ref(row: sqlite3.Row) -> DeviceRef:
        return DeviceRef(
            id=row["id"],
            external_id=row["external_id"],
            config=json.loads(row["config"] or "{}"),
            nominal_watts=row["nominal_watts"],
        )

    def forget(self, device_id: int, adapter: str) -> None:
        self.meter.forget(device_id)
        if adapter in self.adapters:
            self.adapters[adapter].forget(device_id)

    # ------------------------------------------------------------------ polling

    async def _poll_loop(self) -> None:
        while True:
            started = self.clock.now()
            try:
                await self.poll_once()
                await self._maybe_rescan()
            except Exception:  # noqa: BLE001 - o loop nunca pode morrer
                log.exception("Falha no ciclo de leitura")
            interval = self.settings.get().poll_interval_sec
            await asyncio.sleep(max(1.0, interval - (self.clock.now() - started)))

    async def poll_once(self) -> None:
        rows = self.db.all("SELECT * FROM devices WHERE enabled = 1")
        semaphore = asyncio.Semaphore(8)

        async def read(row: sqlite3.Row) -> tuple[sqlite3.Row, DeviceReading | None, str | None]:
            adapter = self.adapters.get(row["adapter"])
            if adapter is None:
                return row, None, f"Adaptador '{row['adapter']}' indisponível."
            async with semaphore:
                try:
                    return row, await adapter.read(self.ref(row)), None
                except AdapterError as exc:
                    return row, None, str(exc)
                except Exception as exc:  # noqa: BLE001
                    log.exception("Erro lendo dispositivo %s", row["id"])
                    return row, None, f"Erro inesperado: {exc}"

        results = await asyncio.gather(*(read(r) for r in rows))
        now = self.clock.now()
        for row, reading, error in results:
            # Relê a linha: um comando pode ter mudado o estado durante a leitura.
            current = self.db.one("SELECT * FROM devices WHERE id = ?", (row["id"],))
            if current is not None:
                self._apply_reading(current, reading, error, now)

    def _apply_reading(
        self,
        row: sqlite3.Row,
        reading: DeviceReading | None,
        error: str | None,
        now: float,
        *,
        from_command: bool = False,
    ) -> None:
        device_id = row["id"]
        settings = self.settings.get()
        was_online = bool(row["online"])
        changes: dict[str, Any] = {}

        if reading is not None and reading.online:
            changes.update(online=1, last_seen=int(now), last_error=None, fail_count=0)
            if reading.is_on is not None:
                changes["is_on"] = int(reading.is_on)
            for key in ("power_w", "voltage_v", "current_a"):
                value = getattr(reading, key)
                if value is not None:
                    changes[key] = round(value, 3)
            self._update_protocol_version(row, reading)
            if not was_online:
                self.alerts.resolve("offline", device_id=device_id, now=now)
                if row["last_seen"]:
                    self.log_event(device_id, "system", "online", None, now)
            if (
                not from_command
                and reading.is_on is not None
                and row["is_on"] is not None
                and bool(row["is_on"]) != reading.is_on
            ):
                # Mudou sem passar pelo Cordyhome: botão físico ou outro app.
                self.log_event(device_id, "device", "on" if reading.is_on else "off", None, now)
            if not from_command:
                self.meter.record(device_id, now, self._effective_power(row, reading))
                self._check_power_alert(row, changes.get("power_w"), now)
        else:
            fails = row["fail_count"] + 1
            changes.update(fail_count=fails, last_error=error)
            if fails >= settings.offline_after_failures:
                changes["online"] = 0
                self.meter.record(device_id, now, None)
                if was_online or row["last_seen"] is None:
                    self.alerts.open(
                        "offline",
                        f"{row['name']} está sem comunicação. {error or ''}".strip(),
                        device_id=device_id,
                        severity="warning",
                        now=now,
                    )
                    if was_online:
                        self.log_event(device_id, "system", "offline", error, now)

        assignments = ", ".join(f"{key} = ?" for key in changes)
        self.db.execute(
            f"UPDATE devices SET {assignments} WHERE id = ?", (*changes.values(), device_id)
        )
        updated = self.db.one("SELECT * FROM devices WHERE id = ?", (device_id,))
        if updated is not None and _visible_change(row, updated):
            self.bus.publish("device", device=device_out(updated))

    def _effective_power(self, row: sqlite3.Row, reading: DeviceReading) -> float | None:
        if reading.power_w is not None:
            return reading.power_w
        if reading.is_on and row["nominal_watts"]:
            return float(row["nominal_watts"])
        return 0.0 if reading.is_on is False else None

    def _check_power_alert(self, row: sqlite3.Row, power: float | None, now: float) -> None:
        limit = row["power_alert_watts"]
        if not limit or power is None:
            return
        if power > limit:
            self.alerts.open(
                "high_power",
                f"{row['name']} está consumindo {power:.0f} W (limite {limit:.0f} W).",
                device_id=row["id"],
                severity="critical",
                now=now,
            )
        elif power < limit * HIGH_POWER_RESOLVE_RATIO:
            self.alerts.resolve("high_power", device_id=row["id"], now=now)

    def _update_protocol_version(self, row: sqlite3.Row, reading: DeviceReading) -> None:
        cfg = json.loads(row["config"] or "{}")
        detected = reading.raw.get("detected_version")
        if row["adapter"] != "tuya" or (cfg.get("version_confirmed") and not detected):
            return
        if detected:
            cfg["version"] = detected
        cfg["version_confirmed"] = True
        self.db.execute("UPDATE devices SET config = ? WHERE id = ?", (json.dumps(cfg), row["id"]))

    async def _maybe_rescan(self) -> None:
        """IP mudou (DHCP)? Procura as tomadas offline na rede de tempos em tempos."""
        if self.lan_rescan is None:
            return
        now = self.clock.now()
        if now - self._last_rescan < LAN_RESCAN_INTERVAL:
            return
        offline = self.db.scalar(
            "SELECT COUNT(*) FROM devices WHERE adapter = 'tuya' AND enabled = 1 AND online = 0"
        )
        if offline:
            self._last_rescan = now
            # Em segundo plano: a varredura de outras redes leva alguns segundos e as
            # leituras das tomadas que estão online não podem esperar por ela.
            self._background(self.lan_rescan())

    # ------------------------------------------------------------------ comandos

    async def set_power(self, device_id: int, on: bool, source: str = "user") -> dict[str, Any]:
        row = self.row(device_id)
        adapter = self.adapters.get(row["adapter"])
        now = self.clock.now()
        verb = "ligar" if on else "desligar"
        try:
            if adapter is None:
                raise AdapterError(f"Adaptador '{row['adapter']}' indisponível.")
            reading = await adapter.set_power(self.ref(row), on)
        except AdapterError as exc:
            self.alerts.record(
                "command_failed",
                f"Não foi possível {verb} {row['name']}: {exc}",
                device_id=device_id,
                severity="warning",
                now=now,
            )
            self.log_event(device_id, source, "failed", f"{verb}: {exc}", now)
            raise
        if reading is None:
            reading = DeviceReading(online=True, is_on=on)
        self._apply_reading(self.row(device_id), reading, None, now, from_command=True)
        self.log_event(device_id, source, "on" if on else "off", None, now)
        self._schedule_refresh(device_id)
        return self.device(device_id)

    async def toggle(self, device_id: int, source: str = "user") -> dict[str, Any]:
        row = self.row(device_id)
        return await self.set_power(device_id, not bool(row["is_on"]), source)

    async def room_power(self, room_id: int, on: bool) -> dict[str, Any]:
        # Aparelhos protegidos (ex.: geladeira) nunca são desligados em lote.
        protected = "" if on else " AND confirm_off = 0"
        rows = self.db.all(
            "SELECT id FROM devices WHERE room_id = ? AND enabled = 1 AND online = 1" + protected,
            (room_id,),
        )
        results = await asyncio.gather(
            *(self.set_power(r["id"], on, "room") for r in rows), return_exceptions=True
        )
        failed = [
            r["id"] for r, res in zip(rows, results, strict=True) if isinstance(res, Exception)
        ]
        return {"changed": len(rows) - len(failed), "failed": failed}

    async def refresh(self, device_id: int) -> dict[str, Any]:
        row = self.row(device_id)
        adapter = self.adapters.get(row["adapter"])
        reading, error = None, None
        try:
            if adapter is None:
                raise AdapterError(f"Adaptador '{row['adapter']}' indisponível.")
            reading = await adapter.read(self.ref(row))
        except AdapterError as exc:
            error = str(exc)
        self._apply_reading(self.row(device_id), reading, error, self.clock.now())
        return self.device(device_id)

    def _schedule_refresh(self, device_id: int, delay: float = 2.0) -> None:
        """Depois de um comando, lê de novo para atualizar a potência real."""

        async def run() -> None:
            await asyncio.sleep(delay)
            with contextlib.suppress(DeviceNotFound):
                await self.refresh(device_id)

        self._background(run())

    def _background(self, coro) -> None:
        """Roda uma tarefa sem bloquear o ciclo; erros vão para o log."""

        async def guarded() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("Falha em tarefa de segundo plano")

        try:
            task = asyncio.get_running_loop().create_task(guarded())
        except RuntimeError:
            coro.close()
            return
        self._refresh_tasks.add(task)
        task.add_done_callback(self._refresh_tasks.discard)

    def log_event(
        self, device_id: int, source: str, action: str, detail: str | None, now: float
    ) -> None:
        self.db.execute(
            "INSERT INTO events (device_id, ts, source, action, detail) VALUES (?,?,?,?,?)",
            (device_id, int(now), source, action, detail),
        )

    # ------------------------------------------------------------------ agendamentos

    async def _schedule_loop(self) -> None:
        while True:
            try:
                await self.run_due_schedules()
            except Exception:  # noqa: BLE001
                log.exception("Falha no agendador")
            await asyncio.sleep(15)

    async def run_due_schedules(self) -> None:
        tz = self.settings.get().timezone
        local_now = self.clock.local(tz)
        rows = self.db.all(
            "SELECT s.*, d.name AS device_name, d.is_on AS device_is_on FROM schedules s "
            "JOIN devices d ON d.id = s.device_id WHERE s.enabled = 1 AND d.enabled = 1"
        )
        for row in rows:
            key = due_key(row["time"], row["days"], row["last_run_key"], local_now)
            if key is None:
                continue
            # Marca antes de executar: um comando lento não pode disparar duas vezes.
            self.db.execute(
                "UPDATE schedules SET last_run_key = ?, last_run_at = ? WHERE id = ?",
                (key, int(self.clock.now()), row["id"]),
            )
            on = {"on": True, "off": False}.get(row["action"], not bool(row["device_is_on"]))
            try:
                await self.set_power(row["device_id"], on, "schedule")
                result = "ok"
            except AdapterError as exc:
                result = str(exc)
                self.alerts.record(
                    "schedule_failed",
                    f"Agendamento das {row['time']} não conseguiu "
                    f"{'ligar' if on else 'desligar'} {row['device_name']}.",
                    device_id=row["device_id"],
                    severity="warning",
                    now=self.clock.now(),
                )
            self.db.execute(
                "UPDATE schedules SET last_result = ? WHERE id = ?", (result, row["id"])
            )
            self.bus.publish("schedules")

    # ------------------------------------------------------------------ manutenção

    async def _housekeeping_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                self.meter.flush()
                self.meter.prune(self.clock.now())
                self.db.execute(
                    "DELETE FROM events WHERE ts < ?", (int(self.clock.now()) - 90 * 86400,)
                )
                self.bus.publish("energy")
            except Exception:  # noqa: BLE001
                log.exception("Falha na manutenção")


def _visible_change(before: sqlite3.Row, after: sqlite3.Row) -> bool:
    keys = ("online", "is_on", "power_w", "last_error")
    return any(before[k] != after[k] for k in keys)
