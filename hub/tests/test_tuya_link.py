from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cordyhome.adapters.base import AdapterError
from cordyhome.adapters.tuya import discovery
from cordyhome.adapters.tuya.cloud import CloudDevice
from cordyhome.app import build_services, create_app
from cordyhome.config import Config
from cordyhome.services import tuya_link
from tests.conftest import FakeAdapter

STRATEGY = {
    1: {"status_code": "switch_1", "config_item": {"valueDesc": "{}"}},
    19: {"status_code": "cur_power", "config_item": {"valueDesc": '{"unit":"W","scale":1}'}},
}


class FakeCloud:
    def __init__(self) -> None:
        self.confirmed = False

    async def start_login(self, user_code: str):
        if user_code == "invalido":
            raise AdapterError("Código de usuário inválido.")
        return "tok", "<svg></svg>"

    async def poll_login(self, token: str):
        if not self.confirmed:
            return None
        return {
            "user_code": "abc123",
            "terminal_id": "t",
            "endpoint": "https://example",
            "username": "diego@example.com",
            "token": {
                "t": 0,
                "uid": "u",
                "expire_time": 7200,
                "access_token": "a",
                "refresh_token": "r",
            },
        }

    async def fetch_devices(self, link):
        devices = [
            CloudDevice(
                "dev1", "Geladeira", "cz", "Tomada Steck", "key-1", True, True, STRATEGY, "Cozinha"
            ),
            CloudDevice("dev2", "Abajur", "cz", "Tomada Steck", "key-2", True, True, {}, None),
            CloudDevice("dev3", "Câmera", "sp", "Câmera", "", True, False, {}, "Sala"),
        ]
        return devices, {
            "t": 1,
            "uid": "u",
            "expire_time": 7200,
            "access_token": "a2",
            "refresh_token": "r2",
        }


@pytest.fixture
def fake_cloud():
    return FakeCloud()


@pytest.fixture
def scans():
    return []


@pytest.fixture
def api(fake_cloud, scans, monkeypatch):
    async def fake_scan(scantime=10, want_ids=None, networks=None, keys=None):
        scans.append({"want_ids": want_ids, "networks": networks, "keys": keys})
        return [discovery.LanDevice(id="dev1", ip="192.168.0.50", version=3.4)]

    monkeypatch.setattr(tuya_link, "scan_lan", fake_scan)
    config = Config(data_dir=Path(":memory:"), host="x", port=0, web_dir=None, demo=False)
    svc = build_services(config, adapters={"fake": FakeAdapter()}, tuya_cloud=fake_cloud)
    with TestClient(create_app(config, svc, background=False)) as client:
        client.post("/api/auth/setup", json={"username": "ana", "password": "segredo123"})
        yield client, svc


def test_full_link_and_import_flow(api, fake_cloud):
    client, svc = api
    assert client.post("/api/tuya/login", json={"user_code": "invalido"}).status_code == 502
    r = client.post("/api/tuya/login", json={"user_code": "abc123"})
    assert r.json()["qr_svg"].startswith("<svg")
    assert client.get("/api/tuya/login/tok").json() == {"linked": False}
    fake_cloud.confirmed = True
    assert client.get("/api/tuya/login/tok").json() == {"linked": True}
    assert client.get("/api/tuya").json()["linked"] is True

    candidates = client.get("/api/tuya/devices").json()
    by_id = {c["id"]: c for c in candidates}
    assert by_id["dev1"]["has_energy_meter"] and by_id["dev1"]["lan_ip"] == "192.168.0.50"
    assert by_id["dev2"]["lan_ip"] is None
    assert by_id["dev3"]["local_supported"] is False
    assert "key-1" not in json.dumps(candidates)  # chaves nunca vão para a interface

    # Token renovado pela nuvem é persistido.
    assert svc.settings.get_json("tuya.link")["token"]["access_token"] == "a2"

    r = client.post(
        "/api/tuya/import",
        json={"devices": [{"id": "dev1", "room": "Cozinha"}, {"id": "dev2"}, {"id": "dev3"}]},
    )
    assert len(r.json()["imported"]) == 2  # câmera sem chave local é ignorada

    row = svc.db.one("SELECT * FROM devices WHERE external_id = 'dev1'")
    cfg = json.loads(row["config"])
    assert cfg["local_key"] == "key-1" and cfg["ip"] == "192.168.0.50" and cfg["version"] == 3.4
    assert cfg["dp_map"]["power"] == {"dp": 19, "scale": 1, "unit": "W"}
    assert svc.db.scalar("SELECT name FROM rooms WHERE id = ?", (row["room_id"],)) == "Cozinha"

    # Importar de novo atualiza em vez de duplicar.
    client.get("/api/tuya/devices")
    client.post("/api/tuya/import", json={"devices": [{"id": "dev1"}]})
    assert svc.db.scalar("SELECT COUNT(*) FROM devices WHERE adapter = 'tuya'") == 2

    assert client.delete("/api/tuya").status_code == 204
    assert client.get("/api/tuya").json()["linked"] is False
    assert svc.db.scalar("SELECT COUNT(*) FROM devices") == 2  # aparelhos continuam


def test_scan_covers_configured_networks_with_account_keys(api, fake_cloud, scans):
    client, svc = api
    fake_cloud.confirmed = True
    client.post("/api/tuya/login", json={"user_code": "abc123"})
    client.get("/api/tuya/login/tok")

    client.get("/api/tuya/devices")
    assert scans[-1]["networks"] == []  # sem faixa configurada: só broadcast

    networks = ["192.168.20.7/24", " 192.168.20.0/24"]
    r = client.patch("/api/settings", json={"lan_networks": networks})
    assert r.status_code == 200 and r.json()["lan_networks"] == ["192.168.20.0/24"]
    client.get("/api/tuya/devices")
    assert scans[-1]["networks"] == ["192.168.20.0/24"]
    assert scans[-1]["keys"] == {"dev1": "key-1", "dev2": "key-2"}  # câmera sem chave fica fora

    client.post("/api/tuya/import", json={"devices": [{"id": "dev1"}, {"id": "dev2"}]})
    assert client.post("/api/tuya/rescan").status_code == 200
    assert scans[-1]["keys"] == {"dev1": "key-1", "dev2": "key-2"}
    assert sorted(scans[-1]["want_ids"]) == ["dev1", "dev2"]


@pytest.mark.parametrize("bad", ["8.8.8.0/24", "10.0.0.0/16", "abc", "fd00::/64"])
def test_rejects_invalid_networks(api, bad):
    client, svc = api
    assert client.patch("/api/settings", json={"lan_networks": [bad]}).status_code == 422
    assert svc.settings.get().lan_networks == []


def test_force_scan_uses_networks_and_keys(monkeypatch):
    calls = []

    def fake_devices(**kwargs):
        calls.append(kwargs)
        return {
            "dev1": {"ip": "192.168.20.31", "version": "3.4"},
            "": {"ip": "192.168.20.99", "version": 0.0},  # respondeu mas nenhuma chave serviu
        }

    monkeypatch.setattr(discovery.scanner, "devices", fake_devices)
    found = discovery._scan(1, ["dev1"], ["192.168.20.0/24"], {"dev1": "key-1"})
    assert found == [discovery.LanDevice(id="dev1", ip="192.168.20.31", version=3.4)]
    assert calls[0]["forcescan"] == ["192.168.20.0/24"]
    assert calls[0]["tuyadevices"] == [{"id": "dev1", "key": "key-1", "name": ""}]

    discovery._scan(1, ["dev1"], [], {"dev1": "key-1"})
    assert calls[1]["forcescan"] is False and calls[1]["tuyadevices"] == []
