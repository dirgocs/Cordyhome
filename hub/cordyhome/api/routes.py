from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal
from zoneinfo import ZoneInfo, available_timezones

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from ..services.energy import RANGES, energy_report, power_history, total_power_history
from ..services.scheduler import ALL_DAYS, TIME_RE, next_run
from ..settings import normalize_networks
from .deps import Services, current_user, services, websocket_user

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
ws_router = APIRouter()

DeviceKind = Literal["plug", "light", "switch", "relay", "climate", "other"]


# ============================================================================ visão geral


@router.get("/home")
def home(svc: Services = Depends(services)):
    settings = svc.settings.get()
    now = svc.hub.clock.now()
    devices = svc.hub.devices()
    rooms = svc.db.all("SELECT id, name, sort_order FROM rooms ORDER BY sort_order, name")
    today = energy_report(
        svc.db,
        svc.hub.meter,
        range_key="today",
        tz=settings.timezone,
        now=now,
        tariff=settings.tariff_per_kwh,
    )
    month = energy_report(
        svc.db,
        svc.hub.meter,
        range_key="month",
        tz=settings.timezone,
        now=now,
        tariff=settings.tariff_per_kwh,
    )
    live = sum(d["power_w"] or 0 for d in devices if d["online"])
    return {
        "power_w": live,
        "power_history": _downsample(total_power_history(svc.db, now - 3 * 3600), 300, "w"),
        "today": {"kwh": today["total_kwh"], "cost": today["cost"]},
        "month": {
            "kwh": month["total_kwh"],
            "cost": month["cost"],
            "projected_cost": month["projected_cost"],
        },
        "counts": {
            "total": len(devices),
            "online": sum(d["online"] for d in devices),
            "on": sum(bool(d["online"] and d["is_on"]) for d in devices),
        },
        "unread_alerts": svc.hub.alerts.unread_count(),
        "next_schedules": _schedules(svc)[:3],
        "rooms": [dict(r) for r in rooms],
        "devices": devices,
        "tariff_per_kwh": settings.tariff_per_kwh,
    }


def _downsample(points: list[dict], step: int, key: str) -> list[dict]:
    buckets: dict[int, list[float]] = {}
    for p in points:
        buckets.setdefault(p["ts"] // step * step, []).append(p[key])
    return [{"ts": ts, key: sum(v) / len(v)} for ts, v in sorted(buckets.items())]


# ============================================================================ dispositivos


class DevicePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=60)
    room_id: int | None = None
    kind: DeviceKind | None = None
    enabled: bool | None = None
    nominal_watts: float | None = Field(None, ge=0, le=100_000)
    power_alert_watts: float | None = Field(None, ge=0, le=100_000)
    confirm_off: bool | None = None
    ip: str | None = Field(None, max_length=64)
    protocol_version: float | None = None


class PowerBody(BaseModel):
    on: bool


class ColorBody(BaseModel):
    h: int = Field(ge=0, le=360)
    s: int = Field(ge=0, le=100)
    v: int = Field(ge=1, le=100)


class StateBody(BaseModel):
    brightness: int | None = Field(None, ge=1, le=100)
    color_temp: int | None = Field(None, ge=0, le=100)
    color: ColorBody | None = None


@router.get("/devices")
def list_devices(svc: Services = Depends(services)):
    return svc.hub.devices()


@router.get("/devices/{device_id}")
def get_device(device_id: int, svc: Services = Depends(services)):
    settings = svc.settings.get()
    now = svc.hub.clock.now()
    device = svc.hub.device(device_id)

    def report(range_key: str) -> dict:
        return energy_report(
            svc.db,
            svc.hub.meter,
            range_key=range_key,
            tz=settings.timezone,
            now=now,
            tariff=settings.tariff_per_kwh,
            device_ids=[device_id],
        )

    today, month = report("today"), report("month")
    events = svc.db.all(
        "SELECT ts, source, action, detail FROM events WHERE device_id = ? "
        "ORDER BY ts DESC LIMIT 30",
        (device_id,),
    )
    return {
        **device,
        "energy": {
            "today_kwh": today["total_kwh"],
            "today_cost": today["cost"],
            "month_kwh": month["total_kwh"],
            "month_cost": month["cost"],
            "projected_cost": month["projected_cost"],
            "daily": report("30d")["series"],
        },
        "power_history": _downsample(
            power_history(svc.db, device_id, now - 24 * 3600), 300, "avg_w"
        ),
        "schedules": [s for s in _schedules(svc) if s["device_id"] == device_id],
        "events": [dict(e) for e in events],
    }


@router.patch("/devices/{device_id}")
def patch_device(device_id: int, body: DevicePatch, svc: Services = Depends(services)):
    row = svc.hub.row(device_id)
    changes = body.model_dump(exclude_unset=True)
    config = json.loads(row["config"])
    config_changed = False
    if "ip" in changes:
        config["ip"] = (changes.pop("ip") or "").strip() or None
        config_changed = True
    if "protocol_version" in changes:
        config["version"] = changes.pop("protocol_version")
        config["version_confirmed"] = config["version"] is not None
        config_changed = True
    if "room_id" in changes and changes["room_id"] is not None:
        _ensure_room(svc, changes["room_id"])
    for flag in ("enabled", "confirm_off"):
        if flag in changes:
            changes[flag] = int(changes[flag])
    if config_changed:
        changes["config"] = json.dumps(config)
        svc.hub.forget(device_id, row["adapter"])
    if changes:
        assignments = ", ".join(f"{k} = ?" for k in changes)
        svc.db.execute(
            f"UPDATE devices SET {assignments} WHERE id = ?", (*changes.values(), device_id)
        )
    device = svc.hub.device(device_id)
    svc.bus.publish("device", device=device)
    return device


@router.delete("/devices/{device_id}", status_code=204)
def delete_device(device_id: int, svc: Services = Depends(services)):
    row = svc.hub.row(device_id)
    svc.hub.forget(device_id, row["adapter"])
    svc.db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    svc.bus.publish("devices")


@router.post("/devices/{device_id}/power")
async def device_power(device_id: int, body: PowerBody, svc: Services = Depends(services)):
    return await svc.hub.set_power(device_id, body.on)


@router.post("/devices/{device_id}/state")
async def device_state(device_id: int, body: StateBody, svc: Services = Depends(services)):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(400, "Nada para alterar.")
    return await svc.hub.set_state(device_id, changes)


@router.post("/devices/{device_id}/toggle")
async def device_toggle(device_id: int, svc: Services = Depends(services)):
    return await svc.hub.toggle(device_id)


@router.post("/devices/{device_id}/refresh")
async def device_refresh(device_id: int, svc: Services = Depends(services)):
    return await svc.hub.refresh(device_id)


# ============================================================================ cômodos


class RoomBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class RoomOrder(BaseModel):
    ids: list[int]


def _ensure_room(svc: Services, room_id: int) -> None:
    if not svc.db.scalar("SELECT 1 FROM rooms WHERE id = ?", (room_id,)):
        raise HTTPException(404, "Cômodo não encontrado.")


@router.get("/rooms")
def list_rooms(svc: Services = Depends(services)):
    rows = svc.db.all("SELECT id, name, sort_order FROM rooms ORDER BY sort_order, name")
    return [dict(r) for r in rows]


@router.post("/rooms", status_code=201)
def create_room(body: RoomBody, svc: Services = Depends(services)):
    order = svc.db.scalar("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM rooms")
    cur = svc.db.execute(
        "INSERT INTO rooms (name, sort_order, created_at) VALUES (?,?,?)",
        (body.name.strip(), order, int(time.time())),
    )
    svc.bus.publish("rooms")
    return {"id": cur.lastrowid, "name": body.name.strip(), "sort_order": order}


@router.patch("/rooms/{room_id}")
def rename_room(room_id: int, body: RoomBody, svc: Services = Depends(services)):
    _ensure_room(svc, room_id)
    svc.db.execute("UPDATE rooms SET name = ? WHERE id = ?", (body.name.strip(), room_id))
    svc.bus.publish("rooms")
    return dict(svc.db.one("SELECT id, name, sort_order FROM rooms WHERE id = ?", (room_id,)))


@router.put("/rooms/order")
def reorder_rooms(body: RoomOrder, svc: Services = Depends(services)):
    with svc.db.transaction():
        for index, room_id in enumerate(body.ids):
            svc.db.execute("UPDATE rooms SET sort_order = ? WHERE id = ?", (index, room_id))
    svc.bus.publish("rooms")
    return list_rooms(svc)


@router.delete("/rooms/{room_id}", status_code=204)
def delete_room(room_id: int, svc: Services = Depends(services)):
    _ensure_room(svc, room_id)
    svc.db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
    svc.bus.publish("rooms")


@router.post("/rooms/{room_id}/power")
async def room_power(room_id: int, body: PowerBody, svc: Services = Depends(services)):
    _ensure_room(svc, room_id)
    return await svc.hub.room_power(room_id, body.on)


# ============================================================================ energia


@router.get("/energy")
def energy(
    range: str = Query("today"),  # noqa: A002 - nome do parâmetro na API
    room_id: int | None = None,
    device_id: int | None = None,
    svc: Services = Depends(services),
):
    if range not in RANGES:
        raise HTTPException(422, f"Período inválido. Use: {', '.join(RANGES)}.")
    settings = svc.settings.get()
    device_ids = None
    if device_id is not None:
        device_ids = [device_id]
    elif room_id is not None:
        device_ids = [
            r["id"] for r in svc.db.all("SELECT id FROM devices WHERE room_id = ?", (room_id,))
        ]
    report = energy_report(
        svc.db,
        svc.hub.meter,
        range_key=range,
        tz=settings.timezone,
        now=svc.hub.clock.now(),
        tariff=settings.tariff_per_kwh,
        device_ids=device_ids,
    )
    names = {
        r["id"]: (r["name"], r["room_id"])
        for r in svc.db.all("SELECT id, name, room_id FROM devices")
    }
    rooms: dict[int | None, float] = {}
    for item in report["devices"]:
        name, room = names.get(item["device_id"], ("Dispositivo removido", None))
        item["name"] = name
        item["room_id"] = room
        rooms[room] = rooms.get(room, 0.0) + item["kwh"]
    report["rooms"] = [
        {"room_id": room, "kwh": kwh, "cost": kwh * settings.tariff_per_kwh}
        for room, kwh in sorted(rooms.items(), key=lambda kv: -kv[1])
    ]
    report["tariff_per_kwh"] = settings.tariff_per_kwh
    return report


# ============================================================================ agendamentos


class ScheduleBody(BaseModel):
    device_id: int
    action: Literal["on", "off", "toggle"]
    time: str
    days: int = Field(ALL_DAYS, ge=1, le=ALL_DAYS)
    enabled: bool = True

    @field_validator("time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if not TIME_RE.match(value):
            raise ValueError("Horário deve estar no formato HH:MM.")
        return value


class SchedulePatch(BaseModel):
    action: Literal["on", "off", "toggle"] | None = None
    time: str | None = None
    days: int | None = Field(None, ge=1, le=ALL_DAYS)
    enabled: bool | None = None

    @field_validator("time")
    @classmethod
    def valid_time(cls, value: str | None) -> str | None:
        if value is not None and not TIME_RE.match(value):
            raise ValueError("Horário deve estar no formato HH:MM.")
        return value


def _schedules(svc: Services) -> list[dict[str, Any]]:
    tz = svc.settings.get().timezone
    local_now = svc.hub.clock.local(tz)
    rows = svc.db.all(
        "SELECT s.*, d.name AS device_name, d.room_id FROM schedules s "
        "JOIN devices d ON d.id = s.device_id"
    )
    out = []
    for r in rows:
        nxt = next_run(r["time"], r["days"], local_now) if r["enabled"] else None
        out.append(
            {
                "id": r["id"],
                "device_id": r["device_id"],
                "device_name": r["device_name"],
                "room_id": r["room_id"],
                "action": r["action"],
                "time": r["time"],
                "days": r["days"],
                "enabled": bool(r["enabled"]),
                "next_run": nxt.isoformat() if nxt else None,
                "last_run_at": r["last_run_at"],
                "last_result": r["last_result"],
            }
        )
    return sorted(out, key=lambda s: (s["next_run"] is None, s["next_run"] or "", s["time"]))


@router.get("/schedules")
def list_schedules(svc: Services = Depends(services)):
    return _schedules(svc)


@router.post("/schedules", status_code=201)
def create_schedule(body: ScheduleBody, svc: Services = Depends(services)):
    svc.hub.row(body.device_id)
    cur = svc.db.execute(
        "INSERT INTO schedules (device_id, action, time, days, enabled, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (body.device_id, body.action, body.time, body.days, int(body.enabled), int(time.time())),
    )
    svc.bus.publish("schedules")
    return next(s for s in _schedules(svc) if s["id"] == cur.lastrowid)


@router.patch("/schedules/{schedule_id}")
def patch_schedule(schedule_id: int, body: SchedulePatch, svc: Services = Depends(services)):
    if not svc.db.scalar("SELECT 1 FROM schedules WHERE id = ?", (schedule_id,)):
        raise HTTPException(404, "Agendamento não encontrado.")
    changes = body.model_dump(exclude_unset=True)
    if "enabled" in changes:
        changes["enabled"] = int(changes["enabled"])
    if changes:
        assignments = ", ".join(f"{k} = ?" for k in changes)
        svc.db.execute(
            f"UPDATE schedules SET {assignments} WHERE id = ?", (*changes.values(), schedule_id)
        )
    svc.bus.publish("schedules")
    return next(s for s in _schedules(svc) if s["id"] == schedule_id)


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, svc: Services = Depends(services)):
    svc.db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    svc.bus.publish("schedules")


# ============================================================================ alertas


@router.get("/alerts")
def list_alerts(
    filter: Literal["unread", "all"] = "all",  # noqa: A002
    limit: int = Query(100, ge=1, le=500),
    svc: Services = Depends(services),
):
    where = "WHERE a.acknowledged_at IS NULL" if filter == "unread" else ""
    rows = svc.db.all(
        "SELECT a.*, d.name AS device_name FROM alerts a "
        "LEFT JOIN devices d ON d.id = a.device_id "
        f"{where} ORDER BY a.created_at DESC LIMIT ?",
        (limit,),
    )
    return {
        "unread": svc.hub.alerts.unread_count(),
        "items": [
            {
                "id": r["id"],
                "device_id": r["device_id"],
                "device_name": r["device_name"],
                "kind": r["kind"],
                "severity": r["severity"],
                "message": r["message"],
                "created_at": r["created_at"],
                "resolved_at": r["resolved_at"],
                "acknowledged": r["acknowledged_at"] is not None,
            }
            for r in rows
        ],
    }


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, svc: Services = Depends(services)):
    svc.hub.alerts.acknowledge(alert_id, time.time())
    return {"unread": svc.hub.alerts.unread_count()}


@router.post("/alerts/ack-all")
def ack_all(svc: Services = Depends(services)):
    svc.hub.alerts.acknowledge(None, time.time())
    return {"unread": 0}


# ============================================================================ configurações


class SettingsPatch(BaseModel):
    tariff_per_kwh: float | None = Field(None, ge=0, le=100)
    timezone: str | None = None
    poll_interval_sec: int | None = Field(None, ge=3, le=300)
    offline_after_failures: int | None = Field(None, ge=1, le=20)
    lan_networks: list[str] | None = Field(None, max_length=20)

    @field_validator("lan_networks")
    @classmethod
    def valid_networks(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_networks(value)

    @field_validator("timezone")
    @classmethod
    def valid_tz(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Fuso horário inválido.") from exc
        return value


@router.get("/settings")
def get_settings(svc: Services = Depends(services)):
    return svc.settings.get()


@router.patch("/settings")
def patch_settings(body: SettingsPatch, svc: Services = Depends(services)):
    updated = svc.settings.update(body.model_dump(exclude_unset=True, exclude_none=True))
    svc.bus.publish("settings")
    return updated


@router.get("/timezones")
def timezones():
    return sorted(tz for tz in available_timezones() if "/" in tz and not tz.startswith("Etc"))


# ============================================================================ Tuya


class TuyaLoginBody(BaseModel):
    user_code: str = Field(min_length=4, max_length=64)


class TuyaImportItem(BaseModel):
    id: str
    name: str | None = Field(None, max_length=60)
    room: str | None = Field(None, max_length=40)


class TuyaImportBody(BaseModel):
    devices: list[TuyaImportItem]


@router.get("/tuya")
def tuya_status(svc: Services = Depends(services)):
    return svc.tuya.status()


@router.post("/tuya/login")
async def tuya_login(body: TuyaLoginBody, svc: Services = Depends(services)):
    return await svc.tuya.start_login(body.user_code)


@router.get("/tuya/login/{token}")
async def tuya_login_poll(token: str, svc: Services = Depends(services)):
    return {"linked": await svc.tuya.poll_login(token)}


@router.get("/tuya/devices")
async def tuya_devices(svc: Services = Depends(services)):
    return await svc.tuya.candidates()


@router.post("/tuya/import")
def tuya_import(body: TuyaImportBody, svc: Services = Depends(services)):
    ids = svc.tuya.import_devices([d.model_dump() for d in body.devices])
    return {"imported": ids}


@router.post("/tuya/rescan")
async def tuya_rescan(svc: Services = Depends(services)):
    return {"updated": await svc.tuya.rescan()}


@router.delete("/tuya", status_code=204)
def tuya_unlink(svc: Services = Depends(services)):
    svc.tuya.unlink()


# ============================================================================ MQTT


class MqttConfigBody(BaseModel):
    enabled: bool | None = None
    mode: Literal["embedded", "external"] | None = None
    host: str | None = Field(None, max_length=253)
    port: int | None = Field(None, ge=1, le=65535)
    username: str | None = Field(None, max_length=64)
    password: str | None = Field(None, max_length=128)
    discovery_prefix: str | None = Field(None, min_length=1, max_length=64)


class MqttImportItem(BaseModel):
    id: str
    name: str | None = Field(None, max_length=60)


class MqttImportBody(BaseModel):
    devices: list[MqttImportItem]


@router.get("/mqtt")
def mqtt_status(svc: Services = Depends(services)):
    return svc.mqtt.status()


@router.put("/mqtt")
async def mqtt_configure(body: MqttConfigBody, svc: Services = Depends(services)):
    try:
        return await svc.mqtt.configure(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/mqtt/password")
async def mqtt_new_password(svc: Services = Depends(services)):
    try:
        return await svc.mqtt.new_password()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/mqtt/devices")
def mqtt_devices(svc: Services = Depends(services)):
    return svc.mqtt.candidates()


@router.post("/mqtt/import")
def mqtt_import(body: MqttImportBody, svc: Services = Depends(services)):
    return {"imported": svc.mqtt.import_devices([d.model_dump() for d in body.devices])}


@router.delete("/mqtt", status_code=204)
async def mqtt_disable(svc: Services = Depends(services)):
    await svc.mqtt.disable()


# ============================================================================ tempo real


@ws_router.websocket("/api/ws")
async def events_ws(ws: WebSocket):
    if websocket_user(ws) is None:
        await ws.close(code=4401)
        return
    svc: Services = ws.app.state.services
    await ws.accept()
    queue = svc.bus.subscribe()
    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=25)
            except TimeoutError:
                message = {"type": "ping"}
            await ws.send_json(message)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        svc.bus.unsubscribe(queue)
