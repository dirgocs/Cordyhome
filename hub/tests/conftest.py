from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cordyhome.adapters.base import AdapterError, DeviceReading, DeviceRef
from cordyhome.app import build_services, create_app
from cordyhome.clock import FakeClock
from cordyhome.config import Config

# 2026-01-15 12:00 em São Paulo (UTC-3), uma quinta-feira.
START = 1768489200.0


class FakeAdapter:
    name = "fake"

    def __init__(self) -> None:
        self.power: dict[int, float | None] = {}
        self.on: dict[int, bool] = {}
        self.fail: set[int] = set()

    async def read(self, device: DeviceRef) -> DeviceReading:
        if device.id in self.fail:
            raise AdapterError("Sem resposta na rede.")
        return DeviceReading(
            online=True, is_on=self.on.get(device.id, True), power_w=self.power.get(device.id)
        )

    async def set_power(self, device: DeviceRef, on: bool) -> DeviceReading:
        if device.id in self.fail:
            raise AdapterError("Sem resposta na rede.")
        self.on[device.id] = on
        return DeviceReading(online=True, is_on=on)

    def forget(self, device_id: int) -> None:
        pass

    def capabilities(self, config):
        return config.get("capabilities", ["power"])

    async def set_state(self, device: DeviceRef, changes) -> DeviceReading:
        if device.id in self.fail:
            raise AdapterError("Sem resposta na rede.")
        self.on[device.id] = True
        return DeviceReading(online=True, is_on=True, state=changes)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def adapter() -> FakeAdapter:
    return FakeAdapter()


@pytest.fixture
def svc(clock, adapter):
    config = Config(data_dir=Path(":memory:"), host="127.0.0.1", port=0, web_dir=None, demo=False)
    return build_services(config, adapters={"fake": adapter}, clock=clock)


@pytest.fixture
def client(svc):
    app = create_app(svc.config, svc, background=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed(client):
    r = client.post("/api/auth/setup", json={"username": "ana", "password": "segredo123"})
    assert r.status_code == 200
    return client


def add_device(svc, name="Tomada", **fields) -> int:
    cols = {"name": name, "adapter": "fake", "external_id": name, "config": "{}", "created_at": 0}
    cols.update(fields)
    cur = svc.db.execute(
        f"INSERT INTO devices ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        tuple(cols.values()),
    )
    return cur.lastrowid
