from __future__ import annotations

import asyncio

from cordyhome import __version__
from tests.conftest import add_device


def test_health_reports_version_without_login(client):
    assert client.get("/api/health").json() == {"ok": True, "version": __version__}


def test_setup_login_logout_flow(client):
    assert client.get("/api/auth/status").json()["setup_required"] is True
    assert client.get("/api/devices").status_code == 401
    assert (
        client.post("/api/auth/setup", json={"username": "ana", "password": "curta"}).status_code
        == 422
    )
    client.post("/api/auth/setup", json={"username": "ana", "password": "segredo123"})
    assert client.get("/api/devices").status_code == 200
    assert (
        client.post("/api/auth/setup", json={"username": "x", "password": "segredo123"}).status_code
        == 409
    )
    client.post("/api/auth/logout")
    assert client.get("/api/devices").status_code == 401
    bad = client.post("/api/auth/login", json={"username": "ana", "password": "errada"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login", json={"username": "ANA", "password": "segredo123"})
    assert ok.status_code == 200


def test_login_rate_limit(client):
    client.post("/api/auth/setup", json={"username": "ana", "password": "segredo123"})
    client.post("/api/auth/logout")
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "ana", "password": "errada"})
    r = client.post("/api/auth/login", json={"username": "ana", "password": "segredo123"})
    assert r.status_code == 429


def test_cross_origin_writes_are_blocked(authed, svc):
    device_id = add_device(svc)
    r = authed.post(f"/api/devices/{device_id}/toggle", headers={"origin": "http://evil.example"})
    assert r.status_code == 403


def test_same_origin_behind_proxy_is_allowed(authed, svc):
    device_id = add_device(svc)
    r = authed.post(
        f"/api/devices/{device_id}/toggle",
        headers={
            "origin": "https://casa.tail1234.ts.net",
            "x-forwarded-host": "casa.tail1234.ts.net",
        },
    )
    assert r.status_code == 200


def test_power_command_updates_state_and_logs(authed, svc, adapter):
    device_id = add_device(svc)
    r = authed.post(f"/api/devices/{device_id}/power", json={"on": False})
    assert r.status_code == 200 and r.json()["is_on"] is False
    assert adapter.on[device_id] is False
    detail = authed.get(f"/api/devices/{device_id}").json()
    assert detail["events"][0]["action"] == "off"


def test_failed_command_returns_502_and_records_alert(authed, svc, adapter):
    device_id = add_device(svc)
    adapter.fail.add(device_id)
    r = authed.post(f"/api/devices/{device_id}/power", json={"on": True})
    assert r.status_code == 502
    alerts = authed.get("/api/alerts").json()
    assert alerts["unread"] == 1 and alerts["items"][0]["kind"] == "command_failed"


def test_offline_alert_opens_and_resolves(authed, svc, adapter, clock):
    device_id = add_device(svc, online=1, last_seen=1)
    adapter.fail.add(device_id)
    for _ in range(3):
        asyncio.run(svc.hub.poll_once())
        clock.advance(10)
    device = authed.get(f"/api/devices/{device_id}").json()
    assert device["online"] is False
    items = authed.get("/api/alerts").json()["items"]
    assert [a["kind"] for a in items] == ["offline"] and items[0]["resolved_at"] is None

    adapter.fail.clear()
    asyncio.run(svc.hub.poll_once())
    items = authed.get("/api/alerts").json()["items"]
    assert items[0]["resolved_at"] is not None


def test_high_power_alert(authed, svc, adapter):
    device_id = add_device(svc, power_alert_watts=1000)
    adapter.power[device_id] = 1500
    asyncio.run(svc.hub.poll_once())
    items = authed.get("/api/alerts").json()["items"]
    assert items[0]["kind"] == "high_power" and items[0]["severity"] == "critical"


def test_estimated_power_for_devices_without_meter(authed, svc):
    device_id = add_device(svc, nominal_watts=60)
    asyncio.run(svc.hub.poll_once())
    device = authed.get(f"/api/devices/{device_id}").json()
    assert device["power_w"] == 60 and device["power_estimated"] is True


def test_schedule_fires_once(authed, svc, adapter, clock):
    device_id = add_device(svc)
    local = clock.local("America/Sao_Paulo")
    r = authed.post(
        "/api/schedules",
        json={"device_id": device_id, "action": "off", "time": local.strftime("%H:%M")},
    )
    assert r.status_code == 201
    asyncio.run(svc.hub.run_due_schedules())
    assert adapter.on[device_id] is False
    adapter.on[device_id] = True
    asyncio.run(svc.hub.run_due_schedules())
    assert adapter.on[device_id] is True  # não disparou de novo


def test_schedule_validation(authed, svc):
    device_id = add_device(svc)
    r = authed.post(
        "/api/schedules", json={"device_id": device_id, "action": "on", "time": "25:00"}
    )
    assert r.status_code == 422


def test_rooms_and_room_power(authed, svc, adapter):
    room = authed.post("/api/rooms", json={"name": "Sala"}).json()
    a = add_device(svc, "A", room_id=room["id"], online=1)
    b = add_device(svc, "B", room_id=room["id"], online=1)
    r = authed.post(f"/api/rooms/{room['id']}/power", json={"on": False})
    assert r.json() == {"changed": 2, "failed": []}
    assert adapter.on[a] is False and adapter.on[b] is False
    assert authed.delete(f"/api/rooms/{room['id']}").status_code == 204
    assert authed.get(f"/api/devices/{a}").json()["room_id"] is None


def test_device_detail_never_exposes_local_key(authed, svc):
    device_id = add_device(svc, config='{"local_key": "super-secreta", "ip": "10.0.0.5"}')
    body = authed.get(f"/api/devices/{device_id}").text
    assert "super-secreta" not in body and "10.0.0.5" in body


def test_settings_validation(authed):
    assert authed.patch("/api/settings", json={"timezone": "Marte/Base"}).status_code == 422
    r = authed.patch("/api/settings", json={"tariff_per_kwh": 0.92})
    assert r.json()["tariff_per_kwh"] == 0.92


def test_room_off_skips_protected_devices(authed, svc, adapter):
    room = authed.post("/api/rooms", json={"name": "Cozinha"}).json()
    fridge = add_device(svc, "Geladeira", room_id=room["id"], online=1, confirm_off=1)
    kettle = add_device(svc, "Chaleira", room_id=room["id"], online=1)
    r = authed.post(f"/api/rooms/{room['id']}/power", json={"on": False})
    assert r.json()["changed"] == 1
    assert adapter.on[kettle] is False and fridge not in adapter.on


def test_state_command_for_lights(authed, svc, adapter):
    lamp = add_device(svc, "Abajur", config='{"capabilities": ["power", "brightness", "color"]}')
    plug = add_device(svc, "Tomada")

    r = authed.post(f"/api/devices/{lamp}/state", json={"brightness": 40})
    assert r.status_code == 200
    body = r.json()
    assert body["capabilities"] == ["power", "brightness", "color"]
    assert body["state"] == {"brightness": 40} and body["is_on"] is True

    r = authed.post(f"/api/devices/{lamp}/state", json={"color": {"h": 200, "s": 90, "v": 70}})
    assert r.json()["state"] == {"brightness": 40, "color": {"h": 200, "s": 90, "v": 70}}
    events = authed.get(f"/api/devices/{lamp}").json()["events"]
    assert [e["detail"] for e in events[:2]] == ["cor", "brilho 40%"]

    # Sem a capacidade, ou fora da faixa, o comando é recusado.
    assert authed.post(f"/api/devices/{lamp}/state", json={"color_temp": 50}).status_code == 400
    assert authed.post(f"/api/devices/{plug}/state", json={"brightness": 40}).status_code == 400
    assert authed.post(f"/api/devices/{lamp}/state", json={"brightness": 0}).status_code == 422
    assert authed.post(f"/api/devices/{lamp}/state", json={}).status_code == 400
    assert authed.get(f"/api/devices/{plug}").json()["capabilities"] == ["power"]


def test_device_detail_shows_last_raw_response(authed, svc, adapter, monkeypatch):
    from cordyhome.adapters.base import DeviceReading

    device_id = add_device(svc)

    async def read(device):
        return DeviceReading(online=True, is_on=True, power_w=0, raw={"dps": {"1": True, "19": 0}})

    monkeypatch.setattr(adapter, "read", read)
    authed.post(f"/api/devices/{device_id}/refresh")
    diagnostics = authed.get(f"/api/devices/{device_id}").json()["diagnostics"]
    assert diagnostics["last_response"] == {"1": True, "19": 0}
    assert diagnostics["last_response_at"] is not None
