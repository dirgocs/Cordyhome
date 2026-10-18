from __future__ import annotations

import asyncio

import pytest

from cordyhome.adapters.base import AdapterError, DeviceRef
from cordyhome.adapters.tuya import local


class FakeTinyDevice:
    """Simula uma tomada que só responde no protocolo 3.4."""

    calls: list[tuple[str, float]] = []

    def __init__(self, dev_id, address, local_key, version, **_):
        self.version = version

    def set_socketTimeout(self, _):
        pass

    def updatedps(self, *_args, **_kwargs):
        pass

    def status(self):
        FakeTinyDevice.calls.append(("status", self.version))
        if self.version != 3.4:
            return {"Error": "Check device key or version", "Err": "914"}
        return {"dps": {"1": True, "18": 450, "19": 523, "20": 1268}}

    def set_status(self, on, switch=1):
        return {"dps": {str(switch): on}}

    def set_multiple_values(self, data):
        FakeTinyDevice.calls.append(("set", data))
        return {"dps": {"22": data.get("22", 500)}}  # resposta parcial, como em muitas lâmpadas

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_tinytuya(monkeypatch):
    FakeTinyDevice.calls = []
    monkeypatch.setattr(local.tinytuya, "OutletDevice", FakeTinyDevice)


def ref(**cfg) -> DeviceRef:
    base = {"ip": "10.0.0.2", "local_key": "k", "version": 3.3}
    base.update(cfg)
    return DeviceRef(id=1, external_id="abc", config=base)


def test_detects_protocol_version_and_scales_energy():
    reading = asyncio.run(local.TuyaLocalAdapter().read(ref()))
    assert reading.online and reading.is_on is True
    assert reading.power_w == pytest.approx(52.3)
    assert reading.voltage_v == pytest.approx(126.8)
    assert reading.current_a == pytest.approx(0.45)
    assert reading.raw["detected_version"] == 3.4


def test_confirmed_version_is_not_retried():
    with pytest.raises(AdapterError, match="Chave local"):
        asyncio.run(local.TuyaLocalAdapter().read(ref(version_confirmed=True)))
    assert FakeTinyDevice.calls == [("status", 3.3)]


def test_missing_ip_is_reported_clearly():
    with pytest.raises(AdapterError, match="IP"):
        asyncio.run(local.TuyaLocalAdapter().read(ref(ip=None)))


def test_set_power_uses_mapped_switch_dp():
    adapter = local.TuyaLocalAdapter()
    reading = asyncio.run(adapter.set_power(ref(version=3.4), False))
    assert reading.is_on is False


def test_light_state_command_sends_dps_and_keeps_requested_state():
    from cordyhome.adapters.tuya.dps import DpColour, DpMap, DpRange

    mapping = DpMap(
        switch=20,
        mode=21,
        brightness=DpRange(22, 10, 1000),
        colour=DpColour(24),
        power=None,
    )
    device = ref(version=3.4, version_confirmed=True, dp_map=mapping.to_dict())
    adapter = local.TuyaLocalAdapter()
    assert adapter.capabilities(device.config) == ["power", "brightness", "color"]
    reading = asyncio.run(adapter.set_state(device, {"brightness": 50}))
    assert FakeTinyDevice.calls == [("set", {"20": True, "22": 505, "21": "white"})]
    assert reading.is_on is True and reading.state["brightness"] == 50
